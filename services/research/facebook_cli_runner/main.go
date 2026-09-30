package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync/atomic"
	"time"
	"unicode/utf16"
	"unicode/utf8"

	"github.com/tamnd/facebook-cli/fb"
)

const (
	schemaVersion   = 1
	maxInputBytes   = 64 << 10
	maxOutputBytes  = 16 << 20
	maxResponse     = 4 << 20
	maxRequestURLs  = 100
	maxHTTPRequests = 20
	maxRunDuration  = 5 * time.Minute
	maxRequestTime  = 30 * time.Second
)

var engineVersion = "facebook-cli@v0.3.0+8e251abf0bc6fd28acca9b9fa1cafbd07ccae39"
var activeRunID string

var allowedHosts = map[string]struct{}{
	"facebook.com": {}, "www.facebook.com": {}, "m.facebook.com": {},
}

type request struct {
	SourceType      string   `json:"source_type"`
	RunID           string   `json:"run_id"`
	PageURL         string   `json:"page_url"`
	PostLimit       int      `json:"post_limit"`
	KnownPostURLs   []string `json:"known_post_urls"`
	MaxHTTPRequests int      `json:"max_http_requests"`
	IncludeComments bool     `json:"include_comments"`
}

type envelope struct {
	RunID     string            `json:"run_id"`
	Engine    string            `json:"engine"`
	Tier      int               `json:"tier"`
	Surfaces  []string          `json:"surfaces,omitempty"`
	Sources   []string          `json:"sources,omitempty"`
	Via       map[string]string `json:"via,omitempty"`
	Missed    []fb.Missed       `json:"missed,omitempty"`
	FetchedAt time.Time         `json:"fetched_at,omitempty"`
}

type pageRecord struct {
	ID                 string   `json:"id"`
	Handle             string   `json:"handle,omitempty"`
	Name               string   `json:"name"`
	URL                string   `json:"url"`
	Kind               string   `json:"kind"`
	DelegatePage       string   `json:"delegate_page_id,omitempty"`
	CategoryRaw        string   `json:"category_raw,omitempty"`
	Followers          *int     `json:"followers,omitempty"`
	FollowersPrecision string   `json:"followers_precision,omitempty"`
	Bio                string   `json:"bio,omitempty"`
	Envelope           envelope `json:"provenance"`
}

// groupRecord deliberately excludes descriptions, addresses, image URLs,
// member identities, and discussions. Tier 0 support here is metadata only.
type groupRecord struct {
	ID       string   `json:"id"`
	Name     string   `json:"name"`
	URL      string   `json:"url"`
	Privacy  string   `json:"privacy"`
	Public   bool     `json:"public"`
	Envelope envelope `json:"provenance"`
}

type postCounts struct {
	Reactions *int `json:"reactions"`
	Comments  *int `json:"comments"`
	Shares    *int `json:"shares"`
	Views     *int `json:"views"`
}

type postRecord struct {
	ID                string            `json:"id,omitempty"`
	SourceID          string            `json:"source_id,omitempty"`
	URL               string            `json:"url"`
	AuthorID          string            `json:"author_id,omitempty"`
	DelegatePageID    string            `json:"delegate_page_id,omitempty"`
	PublishedAt       *time.Time        `json:"published_at,omitempty"`
	Text              string            `json:"text"`
	TextTruncated     bool              `json:"text_truncated"`
	Counts            postCounts        `json:"counts"`
	CountsRaw         map[string]string `json:"counts_raw,omitempty"`
	Envelope          envelope          `json:"provenance"`
	ReactionBreakdown map[string]int    `json:"reaction_breakdown,omitempty"`
	Comments          []commentRecord   `json:"comment_records,omitempty"`
	CommentCoverage   commentCoverage   `json:"comment_coverage"`
}

type commentRecord struct {
	ID                  string         `json:"id"`
	AuthorAlias         string         `json:"author_alias"`
	AuthorIdentityKnown bool           `json:"author_identity_known"`
	Text                string         `json:"text"`
	TextTruncated       bool           `json:"text_truncated"`
	PublishedAt         *time.Time     `json:"published_at"`
	Likes               *int           `json:"likes"`
	Reactions           *int           `json:"reactions"`
	ReactionsRaw        string         `json:"reactions_raw,omitempty"`
	ReactionBreakdown   map[string]int `json:"reaction_breakdown,omitempty"`
	ReplyCount          *int           `json:"reply_count"`
}

type commentCoverage struct {
	Mode                  string `json:"mode"`
	ReturnedCount         int    `json:"returned_count"`
	ProviderReportedCount *int   `json:"provider_reported_count"`
	HistoryComplete       bool   `json:"history_complete"`
	NextCursorPresent     bool   `json:"next_cursor_present"`
	RepliesStatus         string `json:"replies_status"`
	StopReason            string `json:"stop_reason"`
}

type output struct {
	SchemaVersion   int          `json:"schema_version"`
	Type            string       `json:"type"`
	Page            *pageRecord  `json:"page,omitempty"`
	Group           *groupRecord `json:"group,omitempty"`
	Post            *postRecord  `json:"post,omitempty"`
	PostsTruncated  bool         `json:"posts_truncated,omitempty"`
	HistoryComplete bool         `json:"history_complete,omitempty"`
	HTTPRequests    int64        `json:"http_requests,omitempty"`
	EngineVersion   string       `json:"engine_version,omitempty"`
	StopReason      string       `json:"stop_reason,omitempty"`
	ErrorCode       int          `json:"error_code,omitempty"`
	FailureKind     string       `json:"failure_kind,omitempty"`
	Error           string       `json:"error,omitempty"`
}

func main() {
	if err := run(); err != nil {
		code := 1
		var coded interface{ ExitCode() int }
		if errors.As(err, &coded) {
			code = coded.ExitCode()
		}
		_ = writeJSON(output{SchemaVersion: schemaVersion, Type: "error", ErrorCode: code,
			FailureKind: failureKind(err), Error: publicError(code)})
		os.Exit(code)
	}
}

func run() error {
	body, err := io.ReadAll(io.LimitReader(os.Stdin, maxInputBytes+1))
	if err != nil || len(body) > maxInputBytes {
		return codedError{code: 2, err: errors.New("invalid input")}
	}
	var in request
	decoder := json.NewDecoder(strings.NewReader(string(body)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&in); err != nil {
		return codedError{code: 2, err: err}
	}
	if in.SourceType == "" {
		in.SourceType = "competitor_facebook_page"
	}
	if in.SourceType != "competitor_facebook_page" && in.SourceType != "facebook_group" {
		return codedError{code: 2, err: errors.New("source_type must be a supported public Facebook source")}
	}
	var sourceRef string
	if in.SourceType == "facebook_group" {
		sourceRef, err = groupReference(in.PageURL)
		if in.PostLimit != 0 {
			return codedError{code: 2, err: errors.New("post_limit must be zero for Tier 0 group metadata")}
		}
	} else {
		sourceRef, err = pageReference(in.PageURL)
		if in.PostLimit < 1 || in.PostLimit > 100 {
			return codedError{code: 2, err: errors.New("post_limit must be between 1 and 100")}
		}
	}
	if err != nil {
		return codedError{code: 2, err: err}
	}
	if !regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`).MatchString(in.RunID) {
		return codedError{code: 2, err: errors.New("run_id is required")}
	}
	activeRunID = in.RunID
	if len(in.KnownPostURLs) > maxRequestURLs {
		return codedError{code: 2, err: errors.New("too many known post URLs")}
	}
	for _, raw := range in.KnownPostURLs {
		if !allowedFacebookURL(raw) {
			return codedError{code: 2, err: errors.New("invalid known post URL")}
		}
	}
	requestBudget := int64(maxHTTPRequests)
	if in.MaxHTTPRequests > 0 && in.MaxHTTPRequests < maxHTTPRequests {
		requestBudget = int64(in.MaxHTTPRequests)
	}

	ctx, cancel := context.WithTimeout(context.Background(), maxRunDuration)
	defer cancel()
	config := fb.Defaults()
	config.Tier = "0"
	config.Cookies = ""
	config.Proxy = ""
	config.Rate = 2 * time.Second
	config.Retries = 2
	config.Timeout = maxRequestTime
	config.NoCache = true
	config.DataDir = filepath.Join(os.TempDir(), "agentic-facebook-cli", in.RunID)
	engine, err := fb.NewEngine(config)
	if err != nil {
		return err
	}
	transport := &boundedTransport{base: http.DefaultTransport.(*http.Transport).Clone(), maxRequests: requestBudget}
	transport.base.Proxy = nil
	transport.base.DisableKeepAlives = true
	transport.base.MaxConnsPerHost = 1
	transport.base.DialContext = publicFacebookDialer(net.DefaultResolver, &net.Dialer{Timeout: maxRequestTime, KeepAlive: -1})
	engine.Client().HTTP = &http.Client{
		Transport:     transport,
		Timeout:       maxRequestTime,
		CheckRedirect: boundedRedirectCallback(transport),
	}
	if in.SourceType == "facebook_group" {
		group, err := engine.Group(ctx, sourceRef)
		if transport.redirectRejected.Load() {
			return codedError{code: 4, err: errRedirectRejected}
		}
		if err != nil {
			return codedError{code: fb.ExitCode(err), err: err}
		}
		if group.ID == "" || strings.TrimSpace(group.Name) == "" || !allowedFacebookURL(group.URL) {
			return codedError{code: 7, err: errors.New("the reference did not resolve to a verified public group")}
		}
		if !group.Visible || !strings.HasPrefix(strings.ToLower(strings.TrimSpace(group.Privacy)), "public") {
			return codedError{code: 9, err: errors.New("the group was not confirmed public")}
		}
		record := &groupRecord{
			ID: group.ID, Name: strings.TrimSpace(group.Name), URL: group.URL,
			Privacy: strings.TrimSpace(group.Privacy), Public: true,
			Envelope: envelopeOf(group.Envelope),
		}
		if err := writeJSON(output{SchemaVersion: schemaVersion, Type: "group", Group: record}); err != nil {
			return err
		}
		return writeJSON(output{
			SchemaVersion: schemaVersion, Type: "summary", HistoryComplete: false,
			HTTPRequests: transport.count.Load(), EngineVersion: engineVersion,
			StopReason: "group_discussions_not_requested_tier0",
		})
	}

	profile, err := engine.Profile(ctx, sourceRef, fb.ProfileOptions{})
	if transport.redirectRejected.Load() {
		return codedError{code: 4, err: errRedirectRejected}
	}
	if err != nil {
		return codedError{code: fb.ExitCode(err), err: err}
	}
	if profile.Kind != "page" && (profile.ID == "" || profile.DelegatePage != profile.ID) {
		return codedError{code: 7, err: errors.New("the reference did not resolve to a verified Page")}
	}
	if profile.ID == "" || !allowedFacebookURL(profile.URL) {
		return codedError{code: 6, err: errors.New("the Page identity is incomplete")}
	}
	page := &pageRecord{
		ID: profile.ID, Handle: profile.Handle, Name: profile.Name, URL: profile.URL,
		Kind: profile.Kind, DelegatePage: profile.DelegatePage, CategoryRaw: profile.CategoryRaw,
		Bio: profile.Bio.Text, Envelope: envelopeOf(profile.Envelope),
	}
	if profile.Followers > 0 {
		page.Followers = intPointer(profile.Followers)
		page.FollowersPrecision = "approximate"
	}
	if err := writeJSON(output{SchemaVersion: schemaVersion, Type: "page", Page: page}); err != nil {
		return err
	}

	// Discover from the verified Page, then read each permalink once. A feed
	// preview often omits the comment edge and some engagement metrics.
	candidates := make([]postRecord, 0, in.PostLimit)
	seen := make(map[string]struct{}, in.PostLimit)
	for _, post := range profile.Posts {
		if record, ok := normalizePost(post, profile.ID); ok {
			if _, exists := seen[record.URL]; exists {
				continue
			}
			seen[record.URL] = struct{}{}
			candidates = append(candidates, record)
			if len(candidates) >= in.PostLimit {
				break
			}
		}
	}
	stopReason := "tier0_feed_exhausted"
	commentBudget := 500
	detailStopped := false
	for i := range candidates {
		if detailStopped {
			if in.IncludeComments {
				markCommentReadUnavailable(&candidates[i], stopReason)
			}
			continue
		}
		post, err := engine.Post(ctx, candidates[i].URL, "")
		if transport.redirectRejected.Load() {
			stopReason, detailStopped = "access_denied", true
			if in.IncludeComments {
				markCommentReadUnavailable(&candidates[i], stopReason)
			}
			continue
		}
		if err != nil {
			reason := failureKind(err)
			if reason == "request_budget_reached" || transport.count.Load() >= requestBudget {
				stopReason, detailStopped = "request_budget_reached", true
				reason = stopReason
			} else if reason == "login_required" || reason == "challenge" || reason == "access_denied" || reason == "rate_limited" {
				stopReason, detailStopped = reason, true
			}
			if in.IncludeComments {
				markCommentReadUnavailable(&candidates[i], reason)
			}
			continue
		}
		record, ok := normalizePost(post, profile.ID)
		if !ok || (candidates[i].ID != "" && record.ID != candidates[i].ID) {
			if in.IncludeComments {
				markCommentReadUnavailable(&candidates[i], "page_identity_unverified")
			}
			continue
		}
		if in.IncludeComments {
			attachComments(&record, post, &commentBudget)
		}
		candidates[i] = record
	}
	for _, postURL := range in.KnownPostURLs {
		if len(candidates) >= in.PostLimit {
			stopReason = "post_limit_reached"
			break
		}
		if detailStopped {
			break
		}
		if _, exists := seen[postURL]; exists {
			continue
		}
		post, err := engine.Post(ctx, postURL, "")
		if transport.redirectRejected.Load() {
			stopReason = "access_denied"
			break
		}
		if err != nil {
			reason := failureKind(err)
			if reason == "request_budget_reached" || transport.count.Load() >= requestBudget {
				stopReason = "request_budget_reached"
				break
			}
			if reason == "login_required" || reason == "challenge" || reason == "access_denied" || reason == "rate_limited" {
				stopReason = reason
				break
			}
			continue
		}
		record, ok := normalizePost(post, profile.ID)
		if !ok {
			continue
		}
		if _, exists := seen[record.URL]; exists {
			continue
		}
		seen[record.URL] = struct{}{}
		if in.IncludeComments {
			attachComments(&record, post, &commentBudget)
		}
		candidates = append(candidates, record)
	}
	for _, record := range candidates {
		if err := writeJSON(output{SchemaVersion: schemaVersion, Type: "post", Post: &record}); err != nil {
			return err
		}
	}

	if err := writeJSON(output{
		SchemaVersion: schemaVersion, Type: "summary", PostsTruncated: profile.PostsTruncated || len(profile.Posts) > in.PostLimit,
		HistoryComplete: false, HTTPRequests: transport.count.Load(), EngineVersion: engineVersion, StopReason: stopReason,
	}); err != nil {
		return err
	}
	return nil
}

func failureKind(err error) string {
	var coded codedError
	var auth *fb.NeedAuthError
	var noResults *fb.NoResultsError
	var httpError *fb.HTTPError
	var rate *fb.RateLimitedError
	var missing *fb.NotFoundError
	var unsupported *fb.UnsupportedError
	var network *fb.NetworkError
	switch {
	case errors.Is(err, errRedirectRejected):
		return "access_denied"
	case errors.As(err, &noResults):
		return "no_posts_returned"
	case errors.As(err, &httpError) && (httpError.Status == http.StatusUnauthorized || httpError.Status == http.StatusForbidden):
		return "access_denied"
	case errors.As(err, &coded) && coded.code == 2:
		return "invalid_request"
	case errors.As(err, &coded) && coded.code == 6:
		return "not_found"
	case errors.As(err, &coded) && coded.code == 7:
		return "page_identity_unverified"
	case errors.As(err, &coded) && coded.code == 9:
		return "group_not_public"
	case errors.Is(err, errRequestBudget):
		return "request_budget_reached"
	case errors.Is(err, errResponseTooLarge):
		return "response_too_large"
	case errors.As(err, &rate):
		return "rate_limited"
	case errors.As(err, &auth):
		message := strings.ToLower(auth.Error())
		switch {
		case strings.Contains(message, "log-in page") || strings.Contains(message, "login page"):
			return "login_required"
		case strings.Contains(message, "blocked the request") || strings.Contains(message, "security") ||
			strings.Contains(message, "checkpoint") || strings.Contains(message, "captcha") ||
			strings.Contains(message, "challenge"):
			return "challenge"
		case strings.Contains(message, "refus") || strings.Contains(message, "allowlist"):
			return "access_denied"
		default:
			return "access_denied"
		}
	case errors.As(err, &missing):
		return "not_found"
	case errors.As(err, &unsupported):
		return "unsupported"
	case errors.As(err, &network):
		return "network_error"
	default:
		return "collector_error"
	}
}

type codedError struct {
	code int
	err  error
}

func (e codedError) Error() string { return e.err.Error() }
func (e codedError) Unwrap() error { return e.err }
func (e codedError) ExitCode() int { return e.code }

var errRequestBudget = errors.New("facebook request budget reached")
var errResponseTooLarge = errors.New("facebook response too large")
var errRedirectRejected = errors.New("Facebook redirect left the permitted host set or exceeded the hop limit")

func publicError(code int) string {
	switch code {
	case 2:
		return "Nguồn Facebook không hợp lệ hoặc cấu hình runner sai."
	case 3:
		return "Facebook không trả bài viết công khai trong lượt này."
	case 4:
		return "Facebook yêu cầu đăng nhập hoặc từ chối đọc dữ liệu công khai."
	case 5:
		return "Facebook giới hạn yêu cầu; hãy thử lại sau."
	case 6:
		return "Không tìm thấy Page hoặc bài viết công khai."
	case 7:
		return "Nguồn không được nhận diện là Fanpage hoặc thao tác không hỗ trợ."
	case 9:
		return "Chỉ hỗ trợ metadata của nhóm được xác nhận là công khai."
	case 8:
		return "Lỗi mạng, giới hạn request hoặc response của Facebook."
	default:
		return "Không thể thu thập dữ liệu Facebook."
	}
}

func pageReference(raw string) (string, error) {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || !allowedFacebookURL(raw) || u.User != nil || u.RawQuery != "" && u.Path != "/profile.php" {
		return "", errors.New("expected an HTTPS Facebook Page URL")
	}
	path := strings.Trim(u.Path, "/")
	if strings.HasPrefix(strings.ToLower(path), "groups/") || strings.Contains(strings.ToLower(path), "events") {
		return "", errors.New("Facebook Groups and events are not Page sources")
	}
	if strings.EqualFold(path, "profile.php") {
		id := u.Query().Get("id")
		if !regexp.MustCompile(`^\d{1,32}$`).MatchString(id) {
			return "", errors.New("profile.php requires a numeric id")
		}
		return id, nil
	}
	if strings.HasPrefix(strings.ToLower(path), "pages/") {
		parts := strings.Split(path, "/")
		if len(parts) >= 3 && regexp.MustCompile(`^\d{1,32}$`).MatchString(parts[len(parts)-1]) {
			return parts[len(parts)-1], nil
		}
		return "", errors.New("unsupported /pages/ URL")
	}
	if path == "" {
		return "", errors.New("Facebook home is not a Page")
	}
	if regexp.MustCompile(`^\d{1,32}$`).MatchString(path) {
		return path, nil
	}
	if strings.Contains(path, "/") || strings.HasSuffix(strings.ToLower(path), ".php") {
		return "", errors.New("expected a Page handle or Page id")
	}
	return path, nil
}

func groupReference(raw string) (string, error) {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || !allowedFacebookURL(raw) || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return "", errors.New("expected an HTTPS public Facebook Group URL")
	}
	parts := strings.Split(strings.Trim(u.Path, "/"), "/")
	if len(parts) != 2 || !strings.EqualFold(parts[0], "groups") ||
		!regexp.MustCompile(`^[A-Za-z0-9._-]{1,128}$`).MatchString(parts[1]) {
		return "", errors.New("expected https://www.facebook.com/groups/{public-id-or-slug}")
	}
	return parts[1], nil
}

func allowedFacebookURL(raw string) bool {
	return allowedFacebookHostURL(raw, false)
}

func allowedFacebookRequestURL(raw string) bool {
	return allowedFacebookHostURL(raw, true)
}

func allowedFacebookHostURL(raw string, allowMirror bool) bool {
	u, err := url.Parse(raw)
	if err != nil || u.Scheme != "https" || u.User != nil || u.Port() != "" && u.Port() != "443" {
		return false
	}
	_, ok := allowedHosts[strings.ToLower(u.Hostname())]
	if ok {
		return true
	}
	return allowMirror && strings.EqualFold(u.Hostname(), "web.facebook.com")
}

func redirectAllowed(req *http.Request, via []*http.Request) error {
	if len(via) >= 5 || !allowedFacebookRequestURL(req.URL.String()) {
		return errRedirectRejected
	}
	if strings.EqualFold(req.URL.Hostname(), "web.facebook.com") {
		if len(via) == 0 {
			return errRedirectRejected
		}
		previousHost := strings.ToLower(via[len(via)-1].URL.Hostname())
		if previousHost != "www.facebook.com" && previousHost != "web.facebook.com" {
			return errRedirectRejected
		}
	}
	return nil
}

func boundedRedirectCallback(transport *boundedTransport) func(*http.Request, []*http.Request) error {
	return func(req *http.Request, via []*http.Request) error {
		if err := redirectAllowed(req, via); err != nil {
			transport.redirectRejected.Store(true)
			return http.ErrUseLastResponse
		}
		return nil
	}
}

type boundedTransport struct {
	base             *http.Transport
	maxRequests      int64
	responseLimit    int64
	count            atomic.Int64
	redirectRejected atomic.Bool
}

func (t *boundedTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if !allowedFacebookRequestURL(req.URL.String()) {
		return nil, errors.New("Facebook request host is outside the allowlist")
	}
	if t.count.Add(1) > t.maxRequests {
		return nil, errRequestBudget
	}
	resp, err := t.base.RoundTrip(req)
	if err != nil {
		return nil, err
	}
	limit := t.responseLimit
	if limit <= 0 {
		limit = maxResponse
	}
	resp.Body = &limitedBody{ReadCloser: resp.Body, max: limit}
	return resp, nil
}

type limitedBody struct {
	io.ReadCloser
	max      int64
	read     int64
	tooLarge bool
}

func (b *limitedBody) Read(p []byte) (int, error) {
	if b.tooLarge {
		return 0, errResponseTooLarge
	}
	remaining := b.max - b.read
	if remaining < 0 {
		remaining = 0
	}
	if int64(len(p)) > remaining+1 {
		p = p[:remaining+1]
	}
	n, err := b.ReadCloser.Read(p)
	b.read += int64(n)
	if b.read > b.max {
		b.tooLarge = true
		return 0, errResponseTooLarge
	}
	return n, err
}

type netIPResolver interface {
	LookupNetIP(context.Context, string, string) ([]netip.Addr, error)
}

func publicFacebookDialer(resolver netIPResolver, dialer *net.Dialer) func(context.Context, string, string) (net.Conn, error) {
	return func(ctx context.Context, network, address string) (net.Conn, error) {
		host, port, err := net.SplitHostPort(address)
		if err != nil || port != "443" {
			return nil, errors.New("Facebook transport requires port 443")
		}
		if _, ok := allowedHosts[strings.ToLower(host)]; !ok && !strings.EqualFold(host, "web.facebook.com") {
			return nil, errors.New("Facebook transport host is outside the allowlist")
		}
		ips, err := resolver.LookupNetIP(ctx, "ip", host)
		if err != nil {
			return nil, err
		}
		for _, ip := range ips {
			ip = ip.Unmap()
			if !publicIP(ip) {
				continue
			}
			conn, dialErr := dialer.DialContext(ctx, network, net.JoinHostPort(ip.String(), port))
			if dialErr == nil {
				return conn, nil
			}
		}
		return nil, errors.New("Facebook host did not resolve to a permitted public IP")
	}
}

func publicIP(ip netip.Addr) bool {
	if !ip.IsValid() || !ip.IsGlobalUnicast() || ip.IsPrivate() || ip.IsLoopback() ||
		ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() || ip.IsMulticast() || ip.IsUnspecified() {
		return false
	}
	blocked := []string{
		"100.64.0.0/10", "192.0.0.0/24", "192.0.2.0/24", "198.18.0.0/15",
		"198.51.100.0/24", "203.0.113.0/24", "240.0.0.0/4", "64:ff9b::/96",
		"2001:db8::/32", "2001:10::/28",
	}
	for _, raw := range blocked {
		prefix := netip.MustParsePrefix(raw)
		if prefix.Contains(ip) {
			return false
		}
	}
	return true
}

func normalizePost(post fb.Post, pageID string) (postRecord, bool) {
	if post.URL == "" || !allowedFacebookURL(post.URL) {
		return postRecord{}, false
	}
	if post.Author.ID != pageID && post.DelegatePage != pageID {
		return postRecord{}, false
	}
	identity := ""
	if decimalID(post.StoryID) {
		identity = post.StoryID
	} else if decimalID(post.ID) {
		identity = post.ID
	}
	var publishedAt *time.Time
	if !post.CreatedAt.IsZero() {
		value := post.CreatedAt.UTC()
		publishedAt = &value
	}
	text := post.Message.Text
	textTruncated := utf8.RuneCountInString(text) > 12000
	if textTruncated {
		end := 0
		for count := 0; count < 12000; count++ {
			_, size := utf8.DecodeRuneInString(text[end:])
			end += size
		}
		text = text[:end]
	}
	counts := postCounts{}
	raw := map[string]string{}
	countsRaw := []struct {
		key, label, raw string
		value           int
		exact           bool
	}{
		{"reactions", "reactions", post.Counts.ReactionsText, post.Counts.Reactions, true},
		{"comments", "comments", "", post.Counts.Comments, true},
		{"shares", "shares", post.Counts.SharesText, post.Counts.Shares, true},
		{"views", "views", "", post.Counts.Views, true},
	}
	for _, item := range countsRaw {
		if item.raw != "" {
			raw[item.key] = item.raw
		}
		if item.value > 0 {
			setMetric(&counts, item.key, item.value)
			continue
		}
		if item.raw != "" {
			if value, ok := parseDisplayCount(item.raw); ok {
				setMetric(&counts, item.key, value)
			}
		}
	}
	if len(raw) == 0 {
		raw = nil
	}
	return postRecord{
		ID: identity, URL: post.URL, AuthorID: post.Author.ID, DelegatePageID: post.DelegatePage,
		PublishedAt: publishedAt, Text: text, TextTruncated: textTruncated, Counts: counts, CountsRaw: raw,
		Envelope: envelopeOf(post.Envelope), ReactionBreakdown: safeReactionBreakdown(post.Counts.ByType),
		CommentCoverage: commentCoverage{Mode: "not_requested", HistoryComplete: false, RepliesStatus: "not_read_tier0", StopReason: "not_requested"},
	}, true
}

func setMetric(counts *postCounts, key string, value int) {
	v := value
	switch key {
	case "reactions":
		counts.Reactions = &v
	case "comments":
		counts.Comments = &v
	case "shares":
		counts.Shares = &v
	case "views":
		counts.Views = &v
	}
}

func parseDisplayCount(raw string) (int, bool) {
	fields := strings.Fields(raw)
	if len(fields) == 0 {
		return 0, false
	}
	value := strings.TrimSpace(fields[0])
	value = strings.TrimSuffix(value, "+")
	multiplier := float64(1)
	hasSuffix := false
	if len(value) > 0 {
		switch strings.ToLower(value[len(value)-1:]) {
		case "k":
			multiplier, value, hasSuffix = 1e3, value[:len(value)-1], true
		case "m":
			multiplier, value, hasSuffix = 1e6, value[:len(value)-1], true
		case "b":
			multiplier, value, hasSuffix = 1e9, value[:len(value)-1], true
		}
	}
	if hasSuffix {
		if strings.Count(value, ",") == 1 && !strings.Contains(value, ".") {
			value = strings.Replace(value, ",", ".", 1)
		} else {
			value = strings.ReplaceAll(value, ",", "")
		}
	} else {
		value = strings.ReplaceAll(strings.ReplaceAll(value, ",", ""), ".", "")
	}
	f, err := strconv.ParseFloat(value, 64)
	if err != nil || f < 0 || f*multiplier > float64(math.MaxInt) {
		return 0, false
	}
	return int(f * multiplier), true
}

func decimalID(value string) bool { return regexp.MustCompile(`^\d{1,40}$`).MatchString(value) }
func envelopeOf(value fb.Envelope) envelope {
	return envelope{RunID: activeRunID, Engine: engineVersion, Tier: value.Tier, Surfaces: value.Surfaces, Sources: value.Sources,
		Via: value.Via, Missed: value.Missed, FetchedAt: value.FetchedAt}
}
func intPointer(value int) *int { return &value }

var outputBytes int

func writeJSON(value output) error {
	line, err := json.Marshal(value)
	if err != nil {
		return err
	}
	if outputBytes+len(line)+1 > maxOutputBytes {
		return errors.New("runner output limit reached")
	}
	line = append(line, '\n')
	n, err := os.Stdout.Write(line)
	outputBytes += n
	return err
}

// Only aggregate reaction counts, never the list of people who reacted.
func safeReactionBreakdown(input map[string]int) map[string]int {
	output := make(map[string]int)
	for rawKey, n := range input {
		key := strings.ToUpper(rawKey)
		switch key {
		case "LIKE", "LOVE", "CARE", "HAHA", "WOW", "SAD", "ANGRY":
			if n >= 0 {
				output[key] = n
			}
		}
	}
	if len(output) == 0 {
		return nil
	}
	return output
}

// Pseudonyms are local to this post/read. No personal author reference leaves
// the process. This is pseudonymization, not a claim of anonymity.
func markCommentReadUnavailable(record *postRecord, reason string) {
	record.Comments = nil
	record.CommentCoverage = commentCoverage{Mode: "unavailable", ProviderReportedCount: record.Counts.Comments,
		HistoryComplete: false, RepliesStatus: "not_read_tier0", StopReason: reason}
}

func attachComments(record *postRecord, post fb.Post, remaining *int) {
	record.CommentCoverage = commentCoverage{Mode: "tier0_embedded", HistoryComplete: false,
		ProviderReportedCount: record.Counts.Comments, NextCursorPresent: post.CommentsCursor != "",
		RepliesStatus: "not_read_tier0", StopReason: "signed_out_embedded_comments"}
	aliases := make(map[string]string)
	seen := make(map[string]struct{})
	names := make([]string, 0, len(post.Comments))
	for _, c := range post.Comments {
		if c.Author.Kind != "page" && c.Author.Name != "" {
			names = append(names, c.Author.Name)
		}
	}
	for _, c := range post.Comments {
		if *remaining <= 0 || len(record.Comments) >= 100 {
			record.CommentCoverage.StopReason = "comment_batch_limit_reached"
			break
		}
		if c.ID == "" || len(c.ID) > 100 || strings.ContainsAny(c.ID, "\r\n\t") {
			continue
		}
		if _, exists := seen[c.ID]; exists {
			continue
		}
		seen[c.ID] = struct{}{}
		authorKey := c.Author.ID
		if authorKey == "" {
			authorKey = "unknown-comment:" + c.ID
		}
		alias, exists := aliases[authorKey]
		if !exists {
			alias = fmt.Sprintf("user_name%02d", len(aliases)+1)
			aliases[authorKey] = alias
		}
		text := maskPersonalMentions(c.Body)
		for _, name := range names {
			text = strings.ReplaceAll(text, name, "[đã che tên cá nhân]")
		}
		runes := []rune(text)
		truncated := len(runes) > 20000
		if truncated {
			text = string(runes[:20000])
		}
		breakdown := safeReactionBreakdown(c.Counts.ByType)
		var likes, reactions, replies *int
		if n, exists := breakdown["LIKE"]; exists {
			likes = intPointer(n)
		}
		if c.Counts.Reactions > 0 {
			reactions = intPointer(c.Counts.Reactions)
		} else if n, ok := parseDisplayCount(c.Counts.ReactionsText); ok {
			reactions = intPointer(n)
		}
		if c.Replies > 0 {
			replies = intPointer(c.Replies)
		}
		var published *time.Time
		if !c.CreatedAt.IsZero() {
			t := c.CreatedAt.UTC()
			published = &t
		}
		record.Comments = append(record.Comments, commentRecord{ID: c.ID, AuthorAlias: alias,
			AuthorIdentityKnown: c.Author.ID != "", Text: text, TextTruncated: truncated, PublishedAt: published,
			Likes: likes, Reactions: reactions, ReactionsRaw: c.Counts.ReactionsText, ReactionBreakdown: breakdown, ReplyCount: replies})
		*remaining--
	}
	record.CommentCoverage.ReturnedCount = len(record.Comments)
}

func maskPersonalMentions(text fb.Text) string {
	units := utf16.Encode([]rune(text.Text))
	hidden := make([]bool, len(units))
	for _, span := range text.Ranges {
		if span.Entity == nil || span.Entity.Kind != "profile" || span.Offset < 0 || span.Length <= 0 || span.Offset >= len(units) {
			continue
		}
		end := span.Offset + span.Length
		if end < span.Offset || end > len(units) {
			end = len(units)
		}
		for i := span.Offset; i < end; i++ {
			hidden[i] = true
		}
	}
	var out strings.Builder
	for i := 0; i < len(units); {
		if hidden[i] {
			out.WriteString("[đã che tên tài khoản]")
			for i < len(units) && hidden[i] {
				i++
			}
			continue
		}
		start := i
		for i < len(units) && !hidden[i] {
			i++
		}
		out.WriteString(string(utf16.Decode(units[start:i])))
	}
	return out.String()
}

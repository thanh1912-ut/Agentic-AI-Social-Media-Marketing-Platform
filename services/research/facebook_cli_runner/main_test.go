package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/netip"
	"strings"
	"testing"
	"unicode/utf8"

	"github.com/tamnd/facebook-cli/fb"
)

func TestPageReference(t *testing.T) {
	tests := []struct {
		input string
		want  string
		ok    bool
	}{
		{"https://www.facebook.com/rival-page", "rival-page", true},
		{"https://facebook.com/123456", "123456", true},
		{"https://www.facebook.com/profile.php?id=123456", "123456", true},
		{"https://www.facebook.com/pages/Rival/123456", "123456", true},
		{"https://www.facebook.com/groups/example", "", false},
		{"https://www.facebook.com/", "", false},
		{"http://www.facebook.com/rival-page", "", false},
		{"https://example.com/rival-page", "", false},
	}
	for _, test := range tests {
		got, err := pageReference(test.input)
		if (err == nil) != test.ok || got != test.want {
			t.Errorf("pageReference(%q) = (%q, %v), want (%q, ok=%t)", test.input, got, err, test.want, test.ok)
		}
	}
}

func TestGroupReferenceAcceptsOnlyGroupHomeURLs(t *testing.T) {
	tests := []struct {
		input string
		want  string
		ok    bool
	}{
		{"https://www.facebook.com/groups/123456", "123456", true},
		{"https://m.facebook.com/groups/local-news/", "local-news", true},
		{"https://facebook.com/people/example", "", false},
		{"https://www.facebook.com/groups/example/posts/123", "", false},
		{"https://facebook.com.evil.example/groups/example", "", false},
		{"https://www.facebook.com/groups/example?ref=share", "", false},
		{"http://www.facebook.com/groups/example", "", false},
	}
	for _, test := range tests {
		got, err := groupReference(test.input)
		if (err == nil) != test.ok || got != test.want {
			t.Errorf("groupReference(%q) = (%q, %v), want (%q, ok=%t)", test.input, got, err, test.want, test.ok)
		}
	}
}

func TestFacebookURLAndRedirectAllowlist(t *testing.T) {
	for _, raw := range []string{
		"https://facebook.com/page", "https://www.facebook.com/page", "https://m.facebook.com/page",
	} {
		if !allowedFacebookURL(raw) {
			t.Errorf("expected Facebook URL to be allowed: %s", raw)
		}
	}
	for _, raw := range []string{
		"http://www.facebook.com/page", "https://web.facebook.com/page", "https://facebook.com:444/page",
		"https://facebook.com.evil.example/page", "https://user@facebook.com/page",
	} {
		if allowedFacebookURL(raw) {
			t.Errorf("expected URL to be rejected: %s", raw)
		}
	}
	if !allowedFacebookRequestURL("https://web.facebook.com/rival") {
		t.Fatal("facebook-cli Tier 0 mirror must be accepted for internal requests")
	}
	if allowedFacebookURL("https://web.facebook.com/rival") {
		t.Fatal("the mirror must not be accepted as a user-submitted Page URL")
	}
	request, _ := http.NewRequest(http.MethodGet, "https://example.org/redirect", nil)
	if err := redirectAllowed(request, nil); err == nil {
		t.Fatal("redirect outside Facebook allowlist must stop")
	}
	request, _ = http.NewRequest(http.MethodGet, "https://www.facebook.com/redirect", nil)
	if err := redirectAllowed(request, make([]*http.Request, 5)); err == nil {
		t.Fatal("sixth redirect must stop")
	}
}

func TestTier0MirrorRedirectIsAllowedOnlyFromFacebookWWW(t *testing.T) {
	request, _ := http.NewRequest(http.MethodGet, "https://web.facebook.com/rival?_rdc=1&_rdr", nil)
	previous, _ := http.NewRequest(http.MethodGet, "https://www.facebook.com/rival", nil)
	if err := redirectAllowed(request, []*http.Request{previous}); err != nil {
		t.Fatalf("signed-out www-to-web mirror redirect should be allowed: %v", err)
	}
	external, _ := http.NewRequest(http.MethodGet, "https://evil.example/rival", nil)
	if err := redirectAllowed(external, []*http.Request{previous}); err == nil {
		t.Fatal("external redirect must still be rejected")
	}
}

type testRoundTripper func(*http.Request) (*http.Response, error)

func (fn testRoundTripper) RoundTrip(request *http.Request) (*http.Response, error) {
	return fn(request)
}

type fixedResolver struct{ ips []netip.Addr }

func (resolver fixedResolver) LookupNetIP(context.Context, string, string) ([]netip.Addr, error) {
	return resolver.ips, nil
}

func TestCrossHostRedirectIsStoppedBeforeSecondRequest(t *testing.T) {
	requests := 0
	transport := &boundedTransport{}
	client := &http.Client{
		Transport: testRoundTripper(func(request *http.Request) (*http.Response, error) {
			requests++
			return &http.Response{
				StatusCode: http.StatusFound,
				Header:     http.Header{"Location": []string{"https://evil.example/payload"}},
				Body:       io.NopCloser(strings.NewReader("redirect")),
				Request:    request,
			}, nil
		}),
		CheckRedirect: boundedRedirectCallback(transport),
	}
	response, err := client.Get("https://www.facebook.com/page")
	if err != nil {
		t.Fatal(err)
	}
	_ = response.Body.Close()
	if requests != 1 || !transport.redirectRejected.Load() {
		t.Fatalf("external redirect was not stopped: requests=%d rejected=%t", requests, transport.redirectRejected.Load())
	}
}

func TestPinnedDialerRejectsPrivateDNSAnswer(t *testing.T) {
	dial := publicFacebookDialer(fixedResolver{ips: []netip.Addr{netip.MustParseAddr("127.0.0.1")}}, &net.Dialer{})
	if _, err := dial(context.Background(), "tcp", "www.facebook.com:443"); err == nil {
		t.Fatal("private DNS result must be rejected before dialing")
	}
}

func TestPublicIPRejectsPrivateAndSpecialRanges(t *testing.T) {
	for _, raw := range []string{"127.0.0.1", "10.0.0.1", "169.254.1.1", "192.0.2.1", "198.18.0.1", "240.0.0.1", "::1", "2001:db8::1"} {
		if publicIP(netip.MustParseAddr(raw)) {
			t.Errorf("expected non-public IP to be rejected: %s", raw)
		}
	}
	for _, raw := range []string{"1.1.1.1", "2606:4700:4700::1111"} {
		if !publicIP(netip.MustParseAddr(raw)) {
			t.Errorf("expected public IP to be accepted: %s", raw)
		}
	}
}

func TestBoundedTransportCountsAndLimitsBody(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = io.WriteString(w, "12345")
	}))
	defer server.Close()
	address := server.Listener.Addr().String()
	base := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true}, // test server uses a local certificate
		DialContext: func(ctx context.Context, network, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, network, address)
		},
	}
	transport := &boundedTransport{base: base, maxRequests: 1, responseLimit: 4}
	request, _ := http.NewRequest(http.MethodGet, "https://www.facebook.com/page", nil)
	response, err := transport.RoundTrip(request)
	if err != nil {
		t.Fatal(err)
	}
	_, err = io.ReadAll(response.Body)
	_ = response.Body.Close()
	if !errors.Is(err, errResponseTooLarge) {
		t.Fatalf("expected response-size failure, got %v", err)
	}
	if _, err := transport.RoundTrip(request); !errors.Is(err, errRequestBudget) {
		t.Fatalf("expected request-budget failure, got %v", err)
	}
}

func TestParseDisplayCountKeepsApproximateDisplayValuesReadable(t *testing.T) {
	for _, test := range []struct {
		raw  string
		want int
	}{
		{"1.2K", 1200}, {"1,2K", 1200}, {"1,234", 1234}, {"100+", 100},
	} {
		got, ok := parseDisplayCount(test.raw)
		if !ok || got != test.want {
			t.Errorf("parseDisplayCount(%q) = (%d, %t), want %d", test.raw, got, ok, test.want)
		}
	}
	if _, ok := parseDisplayCount("   "); ok {
		t.Fatal("blank count must be treated as missing")
	}
}

func TestFailureKindPreservesUpstreamAccessClassification(t *testing.T) {
	login := codedError{code: 4, err: &fb.NeedAuthError{Msg: "Facebook answered a log-in page"}}
	if got := failureKind(login); got != "login_required" {
		t.Fatalf("failureKind(login) = %q, want login_required", got)
	}
	challenge := codedError{code: 4, err: &fb.NeedAuthError{Msg: "security checkpoint challenge"}}
	if got := failureKind(challenge); got != "challenge" {
		t.Fatalf("failureKind(challenge) = %q, want challenge", got)
	}
}

func TestNormalizePostRequiresPageOwnershipAndDoesNotTurnMissingZeroIntoMetric(t *testing.T) {
	post := fb.Post{
		ID: "123456789", URL: "https://www.facebook.com/rival/posts/123456789",
		Author: fb.Ref{ID: "page-1"}, Message: fb.Text{Text: "Bài tiếng Việt"},
		Counts: fb.Counts{Reactions: 0, Comments: 0, Shares: 0, Views: 0},
	}
	record, ok := normalizePost(post, "page-1")
	if !ok || record.ID != "123456789" || record.Text != "Bài tiếng Việt" {
		t.Fatalf("expected a normalized Page post, got %#v, ok=%t", record, ok)
	}
	if record.Counts.Reactions != nil || record.Counts.Comments != nil || record.Counts.Shares != nil || record.Counts.Views != nil {
		t.Fatal("unproven zero values must remain missing")
	}
	post.Author.ID = "another-page"
	if _, ok := normalizePost(post, "page-1"); ok {
		t.Fatal("a post from another Page must be rejected")
	}
	if !strings.Contains(engineVersion, "8e251abf0bc6fd28acca9b9fa1cafbd07ccae39") {
		t.Fatalf("engine version does not record the pinned upstream revision: %s", engineVersion)
	}
}

func TestEmbeddedCommentsKeepAggregateMetricsAndScopeAliasesToPost(t *testing.T) {
	post := fb.Post{ID: "456", URL: "https://www.facebook.com/111/posts/456", Author: fb.Ref{ID: "111"},
		Counts: fb.Counts{Comments: 200}, CommentsCursor: "private-cursor-not-exported",
		Comments: []fb.Comment{
			{ID: "c1", Author: fb.Ref{ID: "personal-1", Kind: "profile", Name: "Tên Người Thử"},
				Body: fb.Text{Text: "Tên Người Thử hỏi giá"}, Counts: fb.Counts{Reactions: 9, ByType: map[string]int{"Like": 2, "Love": 7}}, Replies: 3},
			{ID: "c2", Author: fb.Ref{ID: "personal-1", Kind: "profile"}, Body: fb.Text{Text: "Câu hỏi tiếp theo"}},
			{ID: "c3", Body: fb.Text{Text: "Không biết tác giả"}},
		}}
	record, ok := normalizePost(post, "111")
	if !ok {
		t.Fatal("verified Page post rejected")
	}
	budget := 500
	attachComments(&record, post, &budget)
	if len(record.Comments) != 3 || record.Comments[0].AuthorAlias != "user_name01" || record.Comments[1].AuthorAlias != "user_name01" || record.Comments[2].AuthorAlias != "user_name02" {
		t.Fatal("incorrect per-post aliases")
	}
	if *record.Comments[0].Likes != 2 || *record.Comments[0].Reactions != 9 || *record.Comments[0].ReplyCount != 3 {
		t.Fatal("likes must not be substituted by total reactions")
	}
	if record.Comments[1].Likes != nil || record.Comments[1].Reactions != nil || record.Comments[1].ReplyCount != nil {
		t.Fatal("ambiguous zero must stay missing")
	}
	data, _ := json.Marshal(record)
	for _, forbidden := range []string{"personal-1", "Tên Người Thử", "private-cursor-not-exported"} {
		if strings.Contains(string(data), forbidden) {
			t.Fatalf("personal identity/cursor leaked: %s", forbidden)
		}
	}
	if record.CommentCoverage.HistoryComplete || record.CommentCoverage.ReturnedCount != 3 || !record.CommentCoverage.NextCursorPresent {
		t.Fatal("partial coverage must be explicit")
	}
}

func TestCommentBudgetDedupAndUnicodeMentions(t *testing.T) {
	person := fb.Ref{Kind: "profile", ID: "person"}
	post := fb.Post{Comments: []fb.Comment{
		{ID: "one", Body: fb.Text{Text: "😀 An hỏi", Ranges: []fb.Range{{Offset: 3, Length: 2, Entity: &person}}}},
		{ID: "one", Body: fb.Text{Text: "duplicate"}},
		{ID: "two", Body: fb.Text{Text: strings.Repeat("á", 20001)}},
		{ID: "three", Body: fb.Text{Text: "over budget"}},
	}}
	record := postRecord{}
	remaining := 2
	attachComments(&record, post, &remaining)
	if len(record.Comments) != 2 || record.Comments[0].Text != "😀 [đã che tên tài khoản] hỏi" {
		t.Fatal("UTF-16 mention masking/dedup failed")
	}
	if !record.Comments[1].TextTruncated || utf8.RuneCountInString(record.Comments[1].Text) != 20000 {
		t.Fatal("Unicode truncation failed")
	}
	if record.CommentCoverage.StopReason != "comment_batch_limit_reached" || remaining != 0 {
		t.Fatal("budget exceeded")
	}
}

func TestUnavailableCommentReadKeepsPostAndSourceCountWithoutInventingEmptyHistory(t *testing.T) {
	record := postRecord{ID: "456", Text: "Previously received Page post", Counts: postCounts{Comments: intPointer(200)}}
	markCommentReadUnavailable(&record, "login_required")
	if record.Text != "Previously received Page post" || record.ID != "456" {
		t.Fatal("failed comment read must not discard a valid feed post")
	}
	if record.CommentCoverage.Mode != "unavailable" || record.CommentCoverage.StopReason != "login_required" ||
		record.CommentCoverage.HistoryComplete || record.CommentCoverage.ReturnedCount != 0 ||
		*record.CommentCoverage.ProviderReportedCount != 200 {
		t.Fatal("unavailable comment read must preserve its reason and distinct source count")
	}
}

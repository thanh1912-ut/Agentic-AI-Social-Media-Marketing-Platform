/** HTTP DTO aliases generated from the backend OpenAPI document. */

import type { components } from './schema';

type Schemas = components['schemas'];

export type ApiUser = Schemas['UserOut'];
export type ApiWorkspace = Schemas['WorkspaceOut'];
export type ApiSessionResponse = Schemas['SessionResponse'];
export type ApiLoginRequest = Schemas['LoginRequest'];
export type ApiLoginResponse = Schemas['LoginResponse'];
export type ApiForgotPasswordRequest = Schemas['ForgotPasswordRequest'];
export type ApiAcceptInvitationRequest = Schemas['AcceptInvitationRequest'];
export type ApiResetPasswordRequest = Schemas['ResetPasswordRequest'];
export type ApiSelectWorkspaceRequest = Schemas['SelectWorkspaceRequest'];
export type ApiMember = Schemas['MemberOut'];
export type ApiInviteMemberRequest = Schemas['InviteMemberRequest'];
export type ApiInviteMemberResponse = Schemas['InviteMemberResponse'];
export type ApiUploadLimits = Schemas['UploadLimits'];
export type ApiDocumentError = Schemas['DocumentError'];
export type ApiDocument = Schemas['DocumentOut'];
export type ApiJobStep = Schemas['JobStepOut'];
export type ApiJobError = Schemas['JobErrorOut'];
export type ApiJob = Schemas['JobOut'];
export type ApiAcceptedResponse = Schemas['AcceptedResponse'];
export type ApiJobEvent = Schemas['JobEventOut'];
export type ApiBrandProfile = Schemas['BrandProfileOut'];
export type ApiBrandProfileField = Schemas['BrandProfileFieldOut'];
export type ApiBrandProfileRevision = Schemas['BrandProfileRevisionOut'];
export type ApiProfileAlternative = Schemas['ProfileAlternativeOut'];
export type ApiProfileFieldUpdate = Schemas['ProfileFieldUpdate'];
export type ApiProfileProvenance = Schemas['ProfileProvenanceOut'];
export type ApiUpdateBrandProfileRequest = Schemas['UpdateBrandProfileRequest'];
export type ApiConfirmBrandProfileRequest = Schemas['ConfirmBrandProfileRequest'];
export type ApiMetricImportRequest = Schemas['MetricImportRequest'];
export type ApiMetricImportResponse = Schemas['MetricImportResponse'];
export type ApiAnalyticsDashboard = Schemas['AnalyticsDashboardOut'];
export type ApiMetricRecommendation = Schemas['RecommendationOut'];

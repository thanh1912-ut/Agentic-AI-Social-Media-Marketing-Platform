type PageBoundWorkspace = {
  page_id?: string | null;
  page_connection_state?: string | null;
} | null | undefined;

export function pageConnectionReady(workspace: PageBoundWorkspace): boolean {
  return workspace?.page_connection_state === 'active' && Boolean(workspace.page_id);
}

export function pageConnectionDisabledReason(workspace: PageBoundWorkspace): string | undefined {
  if (pageConnectionReady(workspace)) return undefined;
  if (workspace?.page_connection_state === 'needs_reconnect') {
    return 'Owner cần kết nối lại đúng Fanpage trong Cài đặt doanh nghiệp trước khi tiếp tục.';
  }
  return 'Owner cần kết nối và xác minh Fanpage doanh nghiệp trong Cài đặt trước khi tiếp tục.';
}

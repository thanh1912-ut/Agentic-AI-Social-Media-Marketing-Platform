/**
 * DEMO FIXTURE — Người dùng, workspace, thành viên, tiến độ onboarding.
 *
 * Bối cảnh demo: doanh nghiệp pilot gồm 3 workspace với 3 vai trò KHÁC NHAU,
 * để chỉ bằng việc đổi workspace là thấy ngay UI của owner / editor / viewer:
 * - `WS_FB`     : Nguyễn Thị Hương là CHỦ SỞ HỮU → thấy đủ nút (duyệt, đăng, mời).
 * - `WS_RETAIL` : Hương là BIÊN TẬP VIÊN   → tạo/sửa nội dung, KHÔNG có nút duyệt.
 * - `WS_EMPTY`  : Hương là NGƯỜI XEM       → rỗng + mọi nút bị khoá kèm lý do.
 *
 * Quyền (`permissions`) lấy thẳng từ `ROLE_PERMISSIONS` — không tự bịa danh sách.
 */

import type { Member, SessionResponse, User, Workspace } from '../auth';
import type { OnboardingState } from '../brand';
import type { Permission, WorkspaceRole } from '../enums';
import { ROLE_PERMISSIONS, WORKSPACE_ROLES } from '../enums';
import {
  DEMO_TODAY,
  MEM_EMPTY_OWNER,
  MEM_EMPTY_SUSPENDED,
  MEM_EMPTY_VIEWER,
  MEM_FB_EDITOR,
  MEM_FB_OWNER,
  MEM_FB_VIEWER,
  MEM_RETAIL_EDITOR,
  MEM_RETAIL_INVITED,
  MEM_RETAIL_OWNER,
  USR_EDITOR_MINH,
  USR_INVITED_HA,
  USR_OWNER_HUONG,
  USR_SUSPENDED_TUAN,
  USR_VIEWER_TRANG,
  WS_EMPTY,
  WS_FB,
  WS_RETAIL,
  demoAgo,
  demoAhead,
  type DemoWorkspaceId,
} from './ids';

/**
 * Quyền của một vai trò, sao chép từ `ROLE_PERMISSIONS` thành mảng thường
 * (contract yêu cầu `Permission[]`, không phải readonly).
 */
function permissionsFor(role: WorkspaceRole): Permission[] {
  return [...ROLE_PERMISSIONS[role]];
}

// ---------------------------------------------------------------------------
// Người dùng
// ---------------------------------------------------------------------------

/** 3 người dùng demo, phủ đủ 3 vai trò: owner / editor / viewer. */
export const demoUsers: User[] = [
  {
    id: USR_OWNER_HUONG,
    email: 'huong.nguyen@phobaccohuong.vn',
    full_name: 'Nguyễn Thị Hương',
    avatar_url: 'https://cdn.demo.local/avatars/nguyen-thi-huong.png',
    created_at: demoAgo({ days: 140 }),
    two_factor_enabled: true,
  },
  {
    id: USR_EDITOR_MINH,
    email: 'minh.tran@annhien.vn',
    full_name: 'Trần Văn Minh',
    avatar_url: 'https://cdn.demo.local/avatars/tran-van-minh.png',
    created_at: demoAgo({ days: 96 }),
    two_factor_enabled: false,
  },
  {
    id: USR_VIEWER_TRANG,
    email: 'trang.le@phobaccohuong.vn',
    full_name: 'Lê Thu Trang',
    created_at: demoAgo({ days: 61 }),
    two_factor_enabled: false,
  },
];

/**
 * Workspace của người dùng đang đăng nhập (Nguyễn Thị Hương).
 * `role` + `permissions` khác nhau ở từng workspace → demo được cả 3 mức quyền.
 */
export const demoWorkspaces: Workspace[] = [
  {
    // Chủ sở hữu: có đủ 15 quyền, bao gồm `post:approve` và `publish:create`.
    id: WS_FB,
    name: 'Quán Phở Bắc Cô Hương',
    slug: 'pho-bac-co-huong',
    industry: 'Ăn uống – quán ăn & đồ ăn mang về',
    logo_url: 'https://cdn.demo.local/logos/pho-bac-co-huong.png',
    role: WORKSPACE_ROLES.OWNER,
    permissions: permissionsFor(WORKSPACE_ROLES.OWNER),
    created_at: demoAgo({ days: 138 }),
  },
  {
    // Biên tập viên: 7 quyền, KHÔNG có `post:approve` / `post:reject` / `publish:create`
    // / `connection:manage` / `member:invite` → UI phải ẩn hoặc khoá các nút đó.
    id: WS_RETAIL,
    name: 'Tạp hoá An Nhiên',
    slug: 'tap-hoa-an-nhien',
    industry: 'Bán lẻ – tạp hoá & đồ dùng gia đình',
    logo_url: 'https://cdn.demo.local/logos/tap-hoa-an-nhien.png',
    role: WORKSPACE_ROLES.EDITOR,
    permissions: permissionsFor(WORKSPACE_ROLES.EDITOR),
    created_at: demoAgo({ days: 21 }),
  },
  {
    // Người xem: `permissions: []` → mọi CTA phải khoá kèm lý do "cần quyền…",
    // không được ẩn im lặng. Workspace này cũng rỗng để demo empty state.
    id: WS_EMPTY,
    name: 'Workspace mới – Chưa đặt tên',
    slug: 'workspace-moi',
    role: WORKSPACE_ROLES.VIEWER,
    permissions: permissionsFor(WORKSPACE_ROLES.VIEWER),
    created_at: demoAgo({ days: 2 }),
  },
];

/**
 * Thành viên từng workspace. Phủ đủ `Member.status`: active / invited / suspended,
 * và đủ 3 vai trò trong cùng một workspace (WS_FB).
 */
export const demoMembers: Record<DemoWorkspaceId, Member[]> = {
  [WS_FB]: [
    {
      id: MEM_FB_OWNER,
      user: demoUsers[0]!,
      role: WORKSPACE_ROLES.OWNER,
      status: 'active',
      joined_at: demoAgo({ days: 138 }),
    },
    {
      id: MEM_FB_EDITOR,
      user: demoUsers[1]!,
      role: WORKSPACE_ROLES.EDITOR,
      status: 'active',
      invited_by: USR_OWNER_HUONG,
      joined_at: demoAgo({ days: 92 }),
    },
    {
      id: MEM_FB_VIEWER,
      user: demoUsers[2]!,
      role: WORKSPACE_ROLES.VIEWER,
      status: 'active',
      invited_by: USR_OWNER_HUONG,
      joined_at: demoAgo({ days: 60 }),
    },
  ],
  [WS_RETAIL]: [
    {
      id: MEM_RETAIL_OWNER,
      user: demoUsers[1]!,
      role: WORKSPACE_ROLES.OWNER,
      status: 'active',
      joined_at: demoAgo({ days: 21 }),
    },
    {
      id: MEM_RETAIL_EDITOR,
      user: demoUsers[0]!,
      role: WORKSPACE_ROLES.EDITOR,
      status: 'active',
      invited_by: USR_EDITOR_MINH,
      joined_at: demoAgo({ days: 14 }),
    },
    {
      // Lời mời đang chờ: chưa có `joined_at`, có `invited_email` + ngày hết hạn.
      // UI phải hiện "Đang chờ chấp nhận" và cho gửi lại lời mời.
      id: MEM_RETAIL_INVITED,
      user: {
        id: USR_INVITED_HA,
        email: 'ha.pham@annhien.vn',
        full_name: 'Phạm Thu Hà',
        created_at: demoAgo({ days: 6 }),
      },
      role: WORKSPACE_ROLES.VIEWER,
      status: 'invited',
      invited_by: USR_EDITOR_MINH,
      invited_email: 'ha.pham@annhien.vn',
      invitation_expires_at: demoAhead({ days: 5 }),
    },
  ],
  [WS_EMPTY]: [
    {
      id: MEM_EMPTY_OWNER,
      user: demoUsers[1]!,
      role: WORKSPACE_ROLES.OWNER,
      status: 'active',
      joined_at: demoAgo({ days: 2 }),
    },
    {
      id: MEM_EMPTY_VIEWER,
      user: demoUsers[0]!,
      role: WORKSPACE_ROLES.VIEWER,
      status: 'active',
      invited_by: USR_EDITOR_MINH,
      joined_at: demoAgo({ days: 2 }),
    },
    {
      // Nhân viên cũ đã bị tạm ngưng: vẫn thấy trong danh sách nhưng không còn quyền.
      id: MEM_EMPTY_SUSPENDED,
      user: {
        id: USR_SUSPENDED_TUAN,
        email: 'tuan.do@annhien.vn',
        full_name: 'Đỗ Anh Tuấn',
        created_at: demoAgo({ days: 19 }),
      },
      role: WORKSPACE_ROLES.EDITOR,
      status: 'suspended',
      invited_by: USR_EDITOR_MINH,
      joined_at: demoAgo({ days: 18 }),
    },
  ],
};

/**
 * Tiến độ nhập doanh nghiệp — 3 mức: xong hết / đang làm dở / chưa bắt đầu.
 * UI dùng để render checklist và biết bước nào còn thiếu.
 */
export const demoOnboarding: Record<DemoWorkspaceId, OnboardingState> = {
  // ĐÃ XONG HOÀN TOÀN: 4/4 bước — mọi CTA trong checklist đều ở trạng thái hoàn tất.
  [WS_FB]: {
    steps: [
      {
        key: 'business_info',
        label: 'Nhập thông tin doanh nghiệp',
        status: 'done',
        href: `/workspaces/${WS_FB}/brand`,
      },
      {
        key: 'upload_documents',
        label: 'Tải tài liệu về thương hiệu',
        status: 'done',
        href: `/workspaces/${WS_FB}/documents`,
      },
      {
        key: 'confirm_brand',
        label: 'Xác nhận Brand Profile',
        status: 'done',
        href: `/workspaces/${WS_FB}/brand/confirm`,
      },
      {
        key: 'create_campaign',
        label: 'Tạo chiến dịch đầu tiên',
        status: 'done',
        href: `/workspaces/${WS_FB}/campaigns/new`,
      },
    ],
    completed_count: 4,
    total_count: 4,
  },

  // LÀM DỞ: đã nhập thông tin, đang tải tài liệu; bước tạo campaign bị CHẶN
  // vì Brand Profile chưa xác nhận → demo `blocked` + `blocked_reason`.
  [WS_RETAIL]: {
    steps: [
      {
        key: 'business_info',
        label: 'Nhập thông tin doanh nghiệp',
        status: 'done',
        href: `/workspaces/${WS_RETAIL}/brand`,
      },
      {
        key: 'upload_documents',
        label: 'Tải tài liệu về thương hiệu',
        status: 'in_progress',
        href: `/workspaces/${WS_RETAIL}/documents`,
      },
      {
        key: 'confirm_brand',
        label: 'Xác nhận Brand Profile',
        status: 'todo',
        href: `/workspaces/${WS_RETAIL}/brand/confirm`,
      },
      {
        key: 'create_campaign',
        label: 'Tạo chiến dịch đầu tiên',
        status: 'blocked',
        blocked_reason:
          'Cần xác nhận Brand Profile trước. Hiện còn 6 trường chưa có thông tin.',
        href: `/workspaces/${WS_RETAIL}/campaigns/new`,
      },
    ],
    completed_count: 1,
    total_count: 4,
  },

  // CHƯA BẮT ĐẦU: workspace vừa tạo, 0/4 bước. Người dùng hiện tại chỉ là
  // `viewer` nên mọi bước đều chưa làm được — UI phải nói rõ lý do, không khoá im lặng.
  [WS_EMPTY]: {
    steps: [
      {
        key: 'business_info',
        label: 'Nhập thông tin doanh nghiệp',
        status: 'todo',
        href: `/workspaces/${WS_EMPTY}/brand`,
      },
      {
        key: 'upload_documents',
        label: 'Tải tài liệu về thương hiệu',
        status: 'todo',
        href: `/workspaces/${WS_EMPTY}/documents`,
      },
      {
        key: 'confirm_brand',
        label: 'Xác nhận Brand Profile',
        status: 'todo',
        href: `/workspaces/${WS_EMPTY}/brand/confirm`,
      },
      {
        key: 'create_campaign',
        label: 'Tạo chiến dịch đầu tiên',
        status: 'todo',
        href: `/workspaces/${WS_EMPTY}/campaigns/new`,
      },
    ],
    completed_count: 0,
    total_count: 4,
  },
};

/**
 * Phiên đăng nhập demo (`GET /api/v1/me`): Hương đang mở workspace quán phở.
 * Dùng để mock app shell khi chưa có backend.
 */
export const demoSession: SessionResponse = {
  user: demoUsers[0]!,
  workspaces: demoWorkspaces,
  active_workspace_id: WS_FB,
  // Phiên còn hạn 7 ngày kể từ DEMO_NOW (cố định, không tính theo giờ hệ thống).
  expires_at: demoAhead({ days: 7 }),
};

/** Ngày demo đang được coi là "hôm nay" — export lại cho UI hiển thị nhất quán. */
export const demoToday = DEMO_TODAY;

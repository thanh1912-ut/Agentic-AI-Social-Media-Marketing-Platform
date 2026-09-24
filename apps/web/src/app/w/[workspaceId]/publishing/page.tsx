'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';

import { UnavailableNotice } from '@/components/ui';

export default function PublishingPage() {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="space-y-2">
        <h1 className="text-lg font-semibold text-slate-900">Xuất bản</h1>
        <p className="max-w-3xl text-sm leading-6 text-slate-600">
          Theo dõi quy trình đưa nội dung đã duyệt lên Facebook. Tài khoản này hiện chưa kết nối Meta, vì vậy bạn có thể xuất nội dung và đăng thủ công.
        </p>
      </header>

      <UnavailableNotice
        title="Chưa kết nối Meta"
        reason="Nền tảng chưa được cấp Meta app, quyền Facebook Page và thông tin xác thực để đăng bài tự động."
        remedy="Mở campaign, kiểm tra phiên bản đã duyệt rồi xuất CSV hoặc XLSX. Tệp xuất không tự đăng bài."
        action={(
          <Link
            href={`/w/${workspaceId}/campaigns`}
            className="inline-flex min-h-10 items-center rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900"
          >
            Mở campaign
          </Link>
        )}
      />

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="manual-publish-title">
        <h2 id="manual-publish-title" className="text-base font-semibold text-slate-900">Quy trình thủ công hiện có</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6 text-slate-700">
          <li>Mở campaign và rà soát nội dung cùng trạng thái duyệt của từng phiên bản.</li>
          <li>Xuất CSV hoặc XLSX từ campaign cần đăng, sau đó đăng phiên bản đã duyệt trong Meta Business Suite.</li>
          <li>Sau khi có số liệu, nhập snapshot thủ công để xem hiệu quả theo nguồn và thời điểm đo.</li>
        </ol>
        <div className="mt-4 flex flex-wrap gap-3 text-sm font-medium">
          <Link href={`/w/${workspaceId}/campaigns`} className="text-slate-900 underline underline-offset-4">
            Xem campaign và xuất nội dung
          </Link>
          <Link href={`/w/${workspaceId}/analytics`} className="text-slate-900 underline underline-offset-4">
            Nhập số liệu hiệu quả
          </Link>
        </div>
      </section>
    </div>
  );
}

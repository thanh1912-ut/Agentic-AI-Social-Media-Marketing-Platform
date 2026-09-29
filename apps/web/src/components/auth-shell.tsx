import Link from 'next/link';
import type { ReactNode } from 'react';

import { Icon } from '@/components/icon';
import styles from './auth-shell.module.css';

export function AuthShell({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <main className={styles.shell}>
      <section className={styles.story} aria-label="Agentic Marketing">
        <Link href="/login" className={styles.logo}>
          <span className={styles.logoMark} aria-hidden="true">a</span>
          <span>Agentic<span className={styles.logoSecondary}>Marketing</span></span>
        </Link>
        <div className={styles.storyContent}>
          <span className={styles.eyebrow}>KHÔNG GIAN SÁNG TẠO CỦA BẠN</span>
          <h2>Ý tưởng của bạn.<br />Tiếng nói thương hiệu.</h2>
          <p>Từ hiểu thương hiệu đến viết, duyệt và xuất bản. Giữ mọi bước trong một không gian làm việc.</p>
          <div className={styles.flow} aria-label="Luồng làm việc: thương hiệu, nội dung, duyệt và xuất bản">
            <div className={styles.flowStart}><Icon name="brand" size={21} /><span>Thương hiệu của bạn</span></div>
            <div className={styles.flowLine} aria-hidden="true" />
            <div className={styles.flowCenter}>
              <span className={styles.flowIcon}><Icon name="sparkles" size={22} /></span>
              <div><strong>Nội dung có định hướng</strong><span>AI hỗ trợ · Bạn quyết định</span></div>
            </div>
            <div className={styles.flowLine} aria-hidden="true" />
            <div className={styles.flowEnd}><Icon name="check" size={18} /><span>Duyệt trước khi xuất bản</span></div>
          </div>
        </div>
        <p className={styles.storyFooter}><Icon name="shield" size={16} /> Nội dung của bạn, dưới sự kiểm soát của bạn.</p>
      </section>
      <section className={styles.formPanel} aria-labelledby="auth-title">
        <div className={styles.formContent}>
          <Link href="/login" className={styles.mobileLogo}><span className={styles.logoMark} aria-hidden="true">a</span> Agentic Marketing</Link>
          <header className={styles.formHeader}>
            <h1 id="auth-title">{title}</h1>
            <p>{description}</p>
          </header>
          <div className={styles.formBody}>{children}</div>
          <p className={styles.formFooter}>Một nơi cho thương hiệu, nội dung và đội ngũ của bạn.</p>
        </div>
      </section>
    </main>
  );
}

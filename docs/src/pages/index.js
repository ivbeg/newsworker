import React from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import DocsContents from '@site/src/components/DocsContents';

import styles from './index.module.css';

function HomepageHeader() {
  const {siteConfig} = useDocusaurusContext();
  const logoSrc = useBaseUrl('img/logo.svg');
  return (
    <header className={styles.hero}>
      <img className={styles.heroLogo} src={logoSrc} alt={siteConfig.title} />
      <h1 className={styles.heroTitle}>{siteConfig.title}</h1>
      <p className={styles.heroTagline}>{siteConfig.tagline}</p>
      <p className={styles.heroNote}>
        Extract JSON, RSS, Atom, and more from HTML pages that publish no feed
        of their own.
      </p>
      <pre className={styles.install}>
        {'pip install newsworker\nnewsworker extract "https://example.com/news" --format rss'}
      </pre>
    </header>
  );
}

export default function Home() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout title={siteConfig.title} description={siteConfig.tagline}>
      <HomepageHeader />
      <main>
        <DocsContents />
      </main>
    </Layout>
  );
}

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SourceProvenanceTag from './SourceProvenanceTag';

describe('SourceProvenanceTag', () => {
  it('renders LIVE mode as text', () => {
    render(<SourceProvenanceTag mode="LIVE" fetchedAt="2026-06-02T00:00:00Z" />);
    expect(screen.getByText('LIVE')).toBeInTheDocument();
  });

  it('renders CACHED mode as text', () => {
    render(<SourceProvenanceTag mode="CACHED" fetchedAt="2026-06-02T00:00:00Z" />);
    expect(screen.getByText('CACHED')).toBeInTheDocument();
  });

  it('renders a 官方 chip for source_type=official (authoritative)', () => {
    render(<SourceProvenanceTag mode="LIVE" sourceType="official" fetchedAt="2026-06-02T00:00:00Z" />);
    expect(screen.getByText(/官方/)).toBeInTheDocument();
  });

  it('does NOT render a source-type chip for ordinary web sources', () => {
    render(<SourceProvenanceTag mode="LIVE" sourceType="news" fetchedAt="2026-06-02T00:00:00Z" />);
    expect(screen.queryByText(/官方|问卷|访谈/)).not.toBeInTheDocument();
  });

  it('renders a 问卷 chip for source_type=survey', () => {
    render(
      <SourceProvenanceTag
        mode="INGESTED"
        sourceType="survey"
        fetchedAt="2026-06-02T00:00:00Z"
      />,
    );
    expect(screen.getByText(/问卷/)).toBeInTheDocument();
  });

  it('renders a 访谈 chip for source_type=interview', () => {
    render(
      <SourceProvenanceTag
        mode="INGESTED"
        sourceType="interview"
        fetchedAt="2026-06-02T00:00:00Z"
      />,
    );
    expect(screen.getByText(/访谈/)).toBeInTheDocument();
  });

  it('renders a muted 点评 chip for source_type=review (non-authoritative)', () => {
    render(<SourceProvenanceTag mode="CACHED" sourceType="review" fetchedAt="2026-06-02T00:00:00Z" />);
    const chip = screen.getByText(/点评/);
    expect(chip).toBeInTheDocument();
    // Must NOT carry the authoritative (strong) palette — it is advisory only.
    expect(chip.className).not.toMatch(/strong/);
  });

  it('renders a muted 论坛 chip for source_type=forum (non-authoritative)', () => {
    render(<SourceProvenanceTag mode="CACHED" sourceType="forum" fetchedAt="2026-06-02T00:00:00Z" />);
    const chip = screen.getByText(/论坛/);
    expect(chip).toBeInTheDocument();
    expect(chip.className).not.toMatch(/strong/);
  });

  it('renders INGESTED mode as 已接入 text', () => {
    render(
      <SourceProvenanceTag
        mode="INGESTED"
        sourceType="survey"
        fetchedAt="2026-06-02T00:00:00Z"
      />,
    );
    expect(screen.getByText('已接入')).toBeInTheDocument();
  });

  it('renders a 真实调研数据 marker for INGESTED sources (real imports only)', () => {
    // INGESTED now exclusively means real imported research (legacy fixture
    // rows were migrated to SIMULATED) — the old 示例样本 demo marker would
    // mislabel real data, the inverse honesty bug.
    render(
      <SourceProvenanceTag mode="INGESTED" sourceType="survey" fetchedAt="2026-06-02T00:00:00Z" />,
    );
    expect(screen.getByTestId('ingested-badge')).toHaveTextContent('真实调研数据');
    expect(screen.queryByText(/示例样本/)).not.toBeInTheDocument();
  });

  it('does NOT render demo/research markers for LIVE web sources', () => {
    render(<SourceProvenanceTag mode="LIVE" fetchedAt="2026-06-02T00:00:00Z" />);
    expect(screen.queryByText(/示例样本/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('ingested-badge')).not.toBeInTheDocument();
  });

  it('renders the loud 模拟问卷数据·不参与分档 badge for SIMULATED sources', () => {
    render(
      <SourceProvenanceTag mode="SIMULATED" sourceType="survey" fetchedAt="2026-06-02T00:00:00Z" />,
    );
    expect(screen.getByTestId('simulated-badge')).toHaveTextContent('模拟问卷数据');
    expect(screen.getByTestId('simulated-badge')).toHaveTextContent('不参与分档');
    expect(screen.getByText('模拟')).toBeInTheDocument();
  });

  it('does NOT render the simulated badge for INGESTED (real ingestion keeps its lift)', () => {
    render(
      <SourceProvenanceTag mode="INGESTED" sourceType="survey" fetchedAt="2026-06-02T00:00:00Z" />,
    );
    expect(screen.queryByTestId('simulated-badge')).not.toBeInTheDocument();
  });
});

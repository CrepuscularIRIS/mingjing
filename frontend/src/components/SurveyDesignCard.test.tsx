import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SurveyDesignCard } from './SurveyDesignCard';

const DESIGN = {
  survey_id: 'SV-1',
  competitor: 'Notion',
  goal: 'g',
  questions: [
    { id: 'q1', text: '您是否使用 Notion？', field: null },
    { id: 'q2', text: '满意度？', field: 'user_sentiment' },
  ],
};

describe('SurveyDesignCard', () => {
  it('renders the designed questions with field tags', () => {
    render(<SurveyDesignCard design={DESIGN} />);
    expect(screen.getByText(/问卷设计/)).toBeInTheDocument();
    expect(screen.getByText('满意度？')).toBeInTheDocument();
    expect(screen.getByText('user_sentiment')).toBeInTheDocument();
  });

  it('renders a demo-data caveat (responses are curated samples, not real research)', () => {
    render(<SurveyDesignCard design={DESIGN} />);
    expect(screen.getByText(/示例数据|示例样本/)).toBeInTheDocument();
  });

  it('renders nothing when design is empty', () => {
    const { container } = render(<SurveyDesignCard design={{}} />);
    expect(container).toBeEmptyDOMElement();
  });
});

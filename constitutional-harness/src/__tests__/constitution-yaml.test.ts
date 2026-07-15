import * as fs from 'fs';
import * as path from 'path';
import { parse } from 'yaml';

interface CitationRecord {
  source_id: string;
  ref: string | null;
  needs_scholar_review: boolean;
}

interface PrincipleRecord {
  id: string;
  needs_scholar_review: boolean;
  source_citations: CitationRecord[];
}

interface ConstitutionDocument {
  version: string;
  track: string;
  status: string;
  principles: PrincipleRecord[];
}

const PAPERS_DIR = path.resolve(__dirname, '..', '..', '..', 'papers');

function loadConstitution(filename: string): ConstitutionDocument {
  const content = fs.readFileSync(path.join(PAPERS_DIR, filename), 'utf8');
  expect(content).not.toContain('TODO_verse_ref');
  expect(content).not.toContain('TODO_tafsir_ref');
  return parse(content) as ConstitutionDocument;
}

describe.each([
  ['constitution_ashari_v1.yaml', 'constitution_ashari_v1', 'ashari'],
  ['constitution_mutazili_v1.yaml', 'constitution_mutazili_v1', 'mutazili']
])('constitution YAML loading: %s', (filename, version, track) => {
  test('loads with explicit citation-review state', () => {
    const constitution = loadConstitution(filename);

    expect(constitution.version).toBe(version);
    expect(constitution.track).toBe(track);
    expect(constitution.status).toBe('draft_needs_scholar_review');
    expect(constitution.principles.length).toBeGreaterThan(0);

    for (const principle of constitution.principles) {
      expect(principle.needs_scholar_review).toBe(true);
      expect(principle.source_citations.length).toBeGreaterThan(0);
      for (const citation of principle.source_citations) {
        if (citation.ref === null) {
          expect(citation.needs_scholar_review).toBe(true);
        }
      }
    }
  });
});

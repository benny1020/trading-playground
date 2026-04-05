"use client";

import { useEffect, useState } from "react";
import { api, Paper } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { formatDate } from "@/lib/utils";
import {
  FlaskConical,
  ExternalLink,
  RefreshCw,
  Search,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

export default function ResearchPage() {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [search, setSearch] = useState("");
  const [activeTag, setActiveTag] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);

  async function loadPapers() {
    try {
      const res = await api.research.papers();
      setPapers(res.data);
    } catch (_) {
    } finally {
      setLoading(false);
    }
  }

  async function handleFetchPapers() {
    setFetching(true);
    try {
      await api.research.fetchPapers();
      await loadPapers();
    } catch (_) {
    } finally {
      setFetching(false);
    }
  }

  useEffect(() => {
    loadPapers();
  }, []);

  // Collect all tags
  const allTags = Array.from(
    new Set(papers.flatMap((p) => p.tags ?? []))
  ).sort();

  const filtered = papers.filter((p) => {
    const q = search.toLowerCase();
    const matchesSearch =
      !q ||
      p.title.toLowerCase().includes(q) ||
      p.authors.toLowerCase().includes(q) ||
      p.abstract?.toLowerCase().includes(q);
    const matchesTag = !activeTag || (p.tags ?? []).includes(activeTag);
    return matchesSearch && matchesTag;
  });

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Research</h1>
          <p className="text-sm text-muted mt-0.5">
            {papers.length} academic paper{papers.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={handleFetchPapers}
          loading={fetching}
        >
          <RefreshCw size={14} className={fetching ? "animate-spin" : ""} />
          Fetch New Papers
        </Button>
      </div>

      {/* Search + Tags */}
      <div className="space-y-3">
        <Input
          placeholder="Search papers by title, author, or content..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          leftIcon={<Search size={14} />}
        />
        {allTags.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-muted">Filter:</span>
            <button
              onClick={() => setActiveTag("")}
              className={[
                "px-2.5 py-1 rounded-full text-xs font-medium transition-colors",
                activeTag === ""
                  ? "bg-primary text-white"
                  : "bg-surface border border-border text-muted hover:text-white",
              ].join(" ")}
            >
              All
            </button>
            {allTags.map((tag) => (
              <button
                key={tag}
                onClick={() => setActiveTag(activeTag === tag ? "" : tag)}
                className={[
                  "px-2.5 py-1 rounded-full text-xs font-medium transition-colors",
                  activeTag === tag
                    ? "bg-primary text-white"
                    : "bg-surface border border-border text-muted hover:text-white",
                ].join(" ")}
              >
                {tag}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Papers List */}
      {loading ? (
        <div className="text-muted text-sm">Loading...</div>
      ) : filtered.length === 0 ? (
        <Card className="py-16 text-center">
          <FlaskConical size={32} className="mx-auto mb-3 text-muted" />
          <p className="text-gray-400 font-medium mb-1">No papers found</p>
          <p className="text-sm text-muted mb-4">
            {search || activeTag
              ? "Try adjusting your search or filters"
              : "Fetch new papers to populate the research library"}
          </p>
          {!search && !activeTag && (
            <Button size="sm" onClick={handleFetchPapers} loading={fetching}>
              <RefreshCw size={13} />
              Fetch Papers
            </Button>
          )}
        </Card>
      ) : (
        <div className="space-y-3">
          {filtered.map((paper) => (
            <PaperCard
              key={paper.id}
              paper={paper}
              expanded={expandedId === paper.id}
              onToggle={() =>
                setExpandedId(expandedId === paper.id ? null : paper.id)
              }
              onOpenDetail={() => setSelectedPaper(paper)}
            />
          ))}
        </div>
      )}

      {/* Detail Modal */}
      <Modal
        open={selectedPaper !== null}
        onClose={() => setSelectedPaper(null)}
        title={selectedPaper?.title ?? ""}
        size="xl"
      >
        {selectedPaper && (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm text-muted">{selectedPaper.authors}</p>
                <p className="text-xs text-muted mt-0.5">
                  {formatDate(selectedPaper.published_date)} · {selectedPaper.source}
                </p>
              </div>
              {selectedPaper.url && (
                <a
                  href={selectedPaper.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0"
                >
                  <Button size="sm" variant="outline">
                    <ExternalLink size={12} />
                    Read Paper
                  </Button>
                </a>
              )}
            </div>

            <div className="flex flex-wrap gap-1.5">
              {(selectedPaper.tags ?? []).map((tag) => (
                <Badge key={tag} variant="primary">{tag}</Badge>
              ))}
            </div>

            {selectedPaper.summary && (
              <div className="bg-background border border-border rounded-lg p-4">
                <p className="text-xs text-muted uppercase tracking-wider mb-2">
                  AI Summary
                </p>
                <p className="text-sm text-gray-300 leading-relaxed">
                  {selectedPaper.summary}
                </p>
              </div>
            )}

            {selectedPaper.abstract && (
              <div>
                <p className="text-xs text-muted uppercase tracking-wider mb-2">
                  Abstract
                </p>
                <p className="text-sm text-gray-400 leading-relaxed">
                  {selectedPaper.abstract}
                </p>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}

function PaperCard({
  paper,
  expanded,
  onToggle,
  onOpenDetail,
}: {
  paper: Paper;
  expanded: boolean;
  onToggle: () => void;
  onOpenDetail: () => void;
}) {
  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-4 py-4">
        {/* Title row */}
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <button
              className="text-left text-sm font-semibold text-white hover:text-primary transition-colors line-clamp-2"
              onClick={onOpenDetail}
            >
              {paper.title}
            </button>
            <div className="flex items-center gap-3 mt-1">
              <span className="text-xs text-muted">{paper.authors}</span>
              <span className="text-xs text-muted">·</span>
              <span className="text-xs text-muted">
                {formatDate(paper.published_date)}
              </span>
              {paper.source && (
                <>
                  <span className="text-xs text-muted">·</span>
                  <span className="text-xs text-primary">{paper.source}</span>
                </>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {paper.url && (
              <a
                href={paper.url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
              >
                <Button size="sm" variant="ghost">
                  <ExternalLink size={12} />
                </Button>
              </a>
            )}
            <Button size="sm" variant="ghost" onClick={onToggle}>
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </Button>
          </div>
        </div>

        {/* Tags */}
        {(paper.tags ?? []).length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {paper.tags.map((tag) => (
              <Badge key={tag} variant="primary">{tag}</Badge>
            ))}
          </div>
        )}

        {/* Summary excerpt */}
        {!expanded && paper.summary && (
          <p className="text-xs text-muted mt-2 line-clamp-2 leading-relaxed">
            {paper.summary}
          </p>
        )}
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-border px-4 py-4 space-y-3 bg-background/50">
          {paper.summary && (
            <div>
              <p className="text-xs text-muted uppercase tracking-wider mb-1.5">
                AI Summary
              </p>
              <p className="text-sm text-gray-300 leading-relaxed">
                {paper.summary}
              </p>
            </div>
          )}
          {paper.abstract && (
            <div>
              <p className="text-xs text-muted uppercase tracking-wider mb-1.5">
                Abstract
              </p>
              <p className="text-sm text-gray-400 leading-relaxed">
                {paper.abstract}
              </p>
            </div>
          )}
          <Button size="sm" variant="outline" onClick={onOpenDetail}>
            View Full Details
          </Button>
        </div>
      )}
    </Card>
  );
}

"use client";

import React, { useState, useRef, useCallback } from "react";
import { DocumentDetail, DocumentItem } from "../../lib/types";
import { fetchDocumentDetail, uploadDocument } from "../../lib/race-client";

interface DocumentManagerProps {
  documents: DocumentItem[];
  selectedDocumentId: string | null;
  onSelectDocument: (docId: string | null) => void;
  onDocumentUploaded: (doc: DocumentItem) => void;
  disabled?: boolean;
}

export default function DocumentManager({
  documents,
  selectedDocumentId,
  onSelectDocument,
  onDocumentUploaded,
  disabled = false,
}: DocumentManagerProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [toastMessage, setToastMessage] = useState<{ text: string; type: "success" | "error" | "info" } | null>(null);

  // Library Modal State
  const [showLibraryModal, setShowLibraryModal] = useState(false);
  const [searchFilter, setSearchFilter] = useState("");

  // Chunk Preview Drawer State
  const [previewDoc, setPreviewDoc] = useState<DocumentDetail | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const activeDoc = documents.find((d) => d.id === selectedDocumentId);

  const showToast = useCallback((text: string, type: "success" | "error" | "info" = "info") => {
    setToastMessage({ text, type });
    setTimeout(() => {
      setToastMessage(null);
    }, 4500);
  }, []);

  const handleProcessFile = async (file: File) => {
    const ext = file.name.toLowerCase().slice(file.name.lastIndexOf("."));
    if (ext !== ".txt" && ext !== ".md") {
      showToast("Only .txt and .md files are supported for RAG indexing.", "error");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      showToast("File exceeds the maximum 5MB upload limit.", "error");
      return;
    }

    setIsUploading(true);
    try {
      const doc = await uploadDocument(file);
      onDocumentUploaded(doc);
      onSelectDocument(doc.id);
      showToast(
        doc.deduplicated
          ? `Matched existing indexed document '${doc.filename}' (${doc.chunk_count} chunks).`
          : `Ingested '${doc.filename}' successfully (${doc.chunk_count} chunks embedded via nomic-embed-text).`,
        "success"
      );
    } catch (err) {
      showToast(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (disabled || isUploading) return;
    const file = e.dataTransfer.files?.[0];
    if (file) {
      handleProcessFile(file);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!disabled && !isUploading) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const openPreview = async (docId: string) => {
    setLoadingPreview(true);
    try {
      const detail = await fetchDocumentDetail(docId);
      setPreviewDoc(detail);
    } catch (err) {
      showToast("Failed to fetch chunk details: " + (err instanceof Error ? err.message : String(err)), "error");
    } finally {
      setLoadingPreview(false);
    }
  };

  const filteredDocs = documents.filter((d) =>
    d.filename.toLowerCase().includes(searchFilter.toLowerCase())
  );

  return (
    <div className="w-full space-y-3">
      {/* Toast Notification */}
      {toastMessage && (
        <div
          className={`p-3 rounded-lg text-xs flex items-center justify-between transition-all shadow-lg animate-in fade-in slide-in-from-top-1 ${
            toastMessage.type === "success"
              ? "bg-emerald-950/90 border border-emerald-700/80 text-emerald-200 shadow-emerald-950/30"
              : toastMessage.type === "error"
              ? "bg-rose-950/90 border border-rose-700/80 text-rose-200 shadow-rose-950/30"
              : "bg-zinc-900 border border-zinc-700 text-zinc-200 shadow-black/40"
          }`}
        >
          <div className="flex items-center gap-2">
            <span className="text-sm">
              {toastMessage.type === "success" ? "✓" : toastMessage.type === "error" ? "⚠️" : "ℹ️"}
            </span>
            <span>{toastMessage.text}</span>
          </div>
          <button
            type="button"
            onClick={() => setToastMessage(null)}
            className="text-zinc-400 hover:text-white ml-3 cursor-pointer"
          >
            ✕
          </button>
        </div>
      )}

      {/* Header bar */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-violet-400 animate-pulse" />
          <span className="font-semibold uppercase tracking-wider text-zinc-300 text-[11px] flex items-center gap-1.5">
            Knowledge Base / RAG Context
          </span>
          <span className="text-[10px] text-zinc-500 font-mono">
            Hybrid Dense Vector + BM25 Sparse
          </span>
        </div>

        <div className="flex items-center gap-2">
          {documents.length > 0 && (
            <button
              type="button"
              disabled={disabled}
              onClick={() => setShowLibraryModal(true)}
              className="px-2.5 py-1 rounded bg-zinc-800/80 hover:bg-zinc-700 border border-zinc-700/80 text-zinc-300 hover:text-white text-[11px] font-medium transition-colors cursor-pointer flex items-center gap-1.5 disabled:opacity-50"
            >
              <svg className="w-3.5 h-3.5 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              <span>Library ({documents.length})</span>
            </button>
          )}
        </div>
      </div>

      {/* Active Attached Document or Dropzone */}
      {activeDoc ? (
        <div className="p-3.5 rounded-xl bg-violet-950/40 border border-violet-700/60 shadow-md shadow-violet-950/20 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-9 w-9 rounded-lg bg-violet-900/60 border border-violet-600/60 flex items-center justify-center text-violet-200 text-base shrink-0 shadow-inner">
              📄
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h4 className="font-semibold text-zinc-100 truncate text-sm" title={activeDoc.filename}>
                  {activeDoc.filename}
                </h4>
                <span className="px-2 py-0.5 rounded-full bg-violet-900/80 text-violet-300 font-mono text-[10px] border border-violet-700/80 shrink-0">
                  {activeDoc.chunk_count} chunks
                </span>
                <span className="px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-400 font-mono text-[9px] border border-emerald-800 shrink-0">
                  ATTACHED
                </span>
              </div>
              <p className="text-[11px] text-zinc-400 mt-0.5 truncate font-mono">
                SHA-256: {activeDoc.content_hash.slice(0, 16)}... • Top-5 Chunks retrieved per prompt
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => openPreview(activeDoc.id)}
              disabled={loadingPreview}
              className="px-2.5 py-1 rounded bg-violet-900/50 hover:bg-violet-800 text-violet-200 border border-violet-700/70 text-xs transition-colors cursor-pointer flex items-center gap-1.5"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
              <span>{loadingPreview ? "Loading..." : "Preview Chunks"}</span>
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onSelectDocument(null)}
              className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-rose-950 hover:border-rose-700 hover:text-rose-300 text-zinc-300 border border-zinc-700 text-xs transition-colors cursor-pointer flex items-center gap-1"
              title="Detach document from race"
            >
              <span>Detach</span>
              <span>✕</span>
            </button>
          </div>
        </div>
      ) : (
        /* Modern Drag & Drop Zone */
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => !disabled && !isUploading && fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-4 transition-all cursor-pointer flex flex-col items-center justify-center text-center group ${
            isDragging
              ? "border-violet-500 bg-violet-950/30 scale-[1.008] shadow-lg shadow-violet-950/40"
              : "border-zinc-800 hover:border-zinc-700 bg-zinc-950/40 hover:bg-zinc-900/30"
          } ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md"
            disabled={disabled || isUploading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleProcessFile(file);
              e.target.value = "";
            }}
            className="hidden"
          />

          <div className="flex items-center gap-3">
            <div className={`h-10 w-10 rounded-xl flex items-center justify-center text-lg transition-transform ${
              isDragging ? "bg-violet-600 text-white scale-110" : "bg-zinc-900 border border-zinc-800 text-zinc-400 group-hover:text-violet-400 group-hover:scale-105"
            }`}>
              {isUploading ? (
                <svg className="animate-spin h-5 w-5 text-violet-400" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              )}
            </div>

            <div className="text-left">
              <p className="text-xs font-medium text-zinc-200 group-hover:text-white transition-colors">
                {isUploading ? "Embedding & Ingesting chunks into pgvector..." : "Drag & drop your document here, or click to browse"}
              </p>
              <div className="flex items-center gap-2 mt-1 text-[11px] text-zinc-500">
                <span className="px-1.5 py-0.2 rounded bg-zinc-800 text-zinc-400 font-mono text-[10px]">.TXT</span>
                <span className="px-1.5 py-0.2 rounded bg-zinc-800 text-zinc-400 font-mono text-[10px]">.MD</span>
                <span>• Max 5MB • Automatically chunked & embedded via nomic-embed-text</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Library Selection Modal */}
      {showLibraryModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl max-w-xl w-full p-5 shadow-2xl flex flex-col max-h-[80vh]">
            <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <span className="text-lg">📚</span>
                <h3 className="text-sm font-semibold text-zinc-100">Knowledge Base Documents</h3>
                <span className="text-xs text-zinc-500 font-mono">({documents.length} available)</span>
              </div>
              <button
                type="button"
                onClick={() => setShowLibraryModal(false)}
                className="text-zinc-400 hover:text-white text-sm cursor-pointer p-1"
              >
                ✕
              </button>
            </div>

            {/* Filter Search */}
            <div className="py-3">
              <input
                type="text"
                placeholder="Search documents by name..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-violet-500"
              />
            </div>

            {/* Document List */}
            <div className="flex-1 overflow-y-auto space-y-2 pr-1 my-1">
              {filteredDocs.length === 0 ? (
                <div className="text-center py-8 text-xs text-zinc-500">
                  No matching documents found.
                </div>
              ) : (
                filteredDocs.map((doc) => {
                  const isSelected = doc.id === selectedDocumentId;
                  return (
                    <div
                      key={doc.id}
                      className={`p-3 rounded-xl border transition-all flex items-center justify-between gap-3 ${
                        isSelected
                          ? "bg-violet-950/40 border-violet-600 shadow-sm"
                          : "bg-zinc-950/50 border-zinc-800/80 hover:border-zinc-700"
                      }`}
                    >
                      <div className="min-w-0 flex items-center gap-3">
                        <span className="text-lg shrink-0">📄</span>
                        <div className="min-w-0">
                          <p className="text-xs font-semibold text-zinc-200 truncate">
                            {doc.filename}
                          </p>
                          <p className="text-[10px] text-zinc-500 font-mono truncate mt-0.5">
                            {doc.chunk_count} chunks • Hash: {doc.content_hash.slice(0, 12)}...
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => openPreview(doc.id)}
                          className="px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-[11px] transition-colors cursor-pointer"
                        >
                          Preview
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            onSelectDocument(isSelected ? null : doc.id);
                            setShowLibraryModal(false);
                          }}
                          className={`px-3 py-1 rounded text-[11px] font-medium transition-all cursor-pointer ${
                            isSelected
                              ? "bg-rose-950/80 hover:bg-rose-900 border border-rose-800 text-rose-300"
                              : "bg-violet-600 hover:bg-violet-500 text-white"
                          }`}
                        >
                          {isSelected ? "Detach" : "Attach"}
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            <div className="pt-3 border-t border-zinc-800 flex justify-between items-center text-xs text-zinc-500">
              <span>RAG context is automatically injected into the system prompt.</span>
              <button
                type="button"
                onClick={() => setShowLibraryModal(false)}
                className="px-4 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs transition-colors cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Chunk Inspection Drawer / Modal */}
      {previewDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl max-w-2xl w-full p-5 shadow-2xl flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
              <div>
                <h3 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                  <span>📄</span>
                  <span>{previewDoc.filename}</span>
                  <span className="px-2 py-0.5 rounded-full bg-violet-900 text-violet-300 font-mono text-[10px]">
                    {previewDoc.chunk_count} chunks
                  </span>
                </h3>
                <p className="text-[11px] text-zinc-500 font-mono mt-0.5">
                  Indexed with SHA-256: {previewDoc.content_hash}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setPreviewDoc(null)}
                className="text-zinc-400 hover:text-white text-sm cursor-pointer p-1"
              >
                ✕
              </button>
            </div>

            {/* Chunks List */}
            <div className="flex-1 overflow-y-auto space-y-3 pr-1 my-3">
              {previewDoc.chunks.map((chunk) => (
                <div
                  key={chunk.id}
                  className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800/80 space-y-1.5"
                >
                  <div className="flex items-center justify-between text-[11px] text-zinc-400 border-b border-zinc-900 pb-1.5">
                    <span className="font-mono text-violet-400 font-medium">
                      Chunk #{chunk.chunk_index}
                    </span>
                    <span className="text-[10px] text-zinc-500 font-mono">
                      {chunk.text.length} characters
                    </span>
                  </div>
                  <pre className="text-xs text-zinc-300 font-sans whitespace-pre-wrap leading-relaxed select-text">
                    {chunk.text}
                  </pre>
                </div>
              ))}
            </div>

            <div className="pt-3 border-t border-zinc-800 flex justify-end">
              <button
                type="button"
                onClick={() => setPreviewDoc(null)}
                className="px-4 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs transition-colors cursor-pointer"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

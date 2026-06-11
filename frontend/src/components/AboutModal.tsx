// About modal - the exact Pulse Header.tsx pattern: 160px icon, product
// name, "Community Edition — vX.Y.Z" and the FULL licence text. Version
// comes from /api/v1/info and the licence body from /api/v1/license (the
// packaged LICENSE file is the single source of truth).

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api } from "../api";

export function AboutModal({ onClose }: { onClose: () => void }) {
  const [version, setVersion] = useState<string>("…");
  const [license, setLicense] = useState<string>("Loading license…");

  useEffect(() => {
    api
      .info()
      .then((info) => setVersion(info.package_version))
      .catch(() => setVersion("dev"));
    fetch("/api/v1/license")
      .then((r) => r.text())
      .then(setLicense)
      .catch(() => setLicense("Elastic License 2.0 — full text unavailable."));
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-[560px] max-w-[92vw] bg-white dark:bg-[#0b1929] rounded-2xl shadow-2xl border border-surface-200/50 dark:border-[#142840] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        data-testid="about-modal"
      >
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-1.5 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300 hover:bg-surface-100 dark:hover:bg-white/10 rounded-lg transition-colors z-10"
        >
          <X size={16} />
        </button>

        <div className="flex flex-col items-center px-8 pt-8 pb-6">
          <img
            src="/logos/nexus-icon.svg"
            alt="Okto Nexus"
            className="w-[160px] h-[160px] object-contain"
          />
          <h2 className="text-xl font-bold text-surface-900 dark:text-white mt-4 font-display">
            Okto Nexus
          </h2>
          <p className="text-sm text-surface-500 dark:text-surface-400 mt-1">
            Community Edition — v{version}
          </p>
          <p className="text-[11px] text-surface-400 dark:text-surface-500 mt-0.5">
            Elastic License 2.0 + SaaS/Branding Addendum + Trademark Policy
          </p>
        </div>

        <div className="border-t border-surface-200/50 dark:border-[#142840] px-8 py-5 max-h-[48vh] overflow-y-auto">
          <h3 className="text-xs font-semibold text-surface-500 dark:text-surface-400 uppercase tracking-wider mb-3 font-display">
            License — Elastic License 2.0
          </h3>
          <div className="text-xs text-surface-600 dark:text-surface-400 leading-relaxed space-y-3">
            <p className="font-medium text-surface-700 dark:text-surface-300 flex items-center gap-2">
              <img src="/logos/oktolabs-icon.svg" alt="Okto Labs" className="h-4 w-4" />
              Copyright 2026 Okto Labs
            </p>
            <pre className="whitespace-pre-wrap font-sans text-[11px] leading-relaxed">
              {license}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}

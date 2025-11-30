from __future__ import annotations

import html
from datetime import datetime

from backend.schemas import AuditResponse


def _fmt_dt(value: datetime | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def render_audit_report(audit: AuditResponse) -> str:
    """Render a simple HTML report from an AuditResponse envelope."""
    escape = html.escape
    header = f"""
    <header style="padding:16px 0; border-bottom:1px solid #e2e8f0;">
      <h1 style="margin:0; font-size:24px; color:#0f172a;">Audit Report: {escape(audit.doc_type)}</h1>
      <p style="margin:4px 0; color:#475569;">Tax Year: {audit.tax_year} &bull; Doc ID: {escape(audit.doc_id)} &bull; Request ID: {escape(audit.request_id)}</p>
      <p style="margin:4px 0; color:#475569;">Received: {_fmt_dt(audit.received_at)} &bull; Processed: {_fmt_dt(audit.processed_at)}</p>
    </header>
    """

    by_sev = audit.summary.by_severity or {}
    summary_section = f"""
    <section style="margin-top:16px; padding:12px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px;">
      <h2 style="margin:0 0 8px 0; font-size:18px; color:#0f172a;">Summary</h2>
      <p style="margin:4px 0; color:#334155;">Total rules evaluated: {audit.summary.total_rules_evaluated}</p>
      <p style="margin:4px 0; color:#334155;">Total findings: {audit.summary.total_findings}</p>
      <div style="margin-top:8px;">
        <strong style="color:#0f172a;">By severity:</strong>
        <ul style="margin:4px 0 0 16px; color:#334155;">
          <li>Error: {by_sev.get('error', 0)}</li>
          <li>Warning: {by_sev.get('warning', 0)}</li>
          <li>Info: {by_sev.get('info', 0)}</li>
        </ul>
      </div>
    </section>
    """

    rows = []
    for f in audit.findings:
        citations = ", ".join(f"{c.label}: {c.url}" for c in f.citations) if f.citations else ""
        fields = ", ".join(f.fields) if f.fields else ""
        rows.append(
            f"""
            <tr style="border-bottom:1px solid #e2e8f0;">
              <td style="padding:8px; color:#0f172a; font-weight:600;">{escape(f.severity)}</td>
              <td style="padding:8px; color:#0f172a;">{escape(f.code)}</td>
              <td style="padding:8px; color:#334155;">{escape(f.rule_type or '')}</td>
              <td style="padding:8px; color:#334155;">{escape(f.category or '')}</td>
              <td style="padding:8px; color:#0f172a; font-weight:600;">{escape(f.summary or f.message)}</td>
              <td style="padding:8px; color:#334155;">{escape(fields)}</td>
              <td style="padding:8px; color:#334155;">{escape(f.message)}</td>
              <td style="padding:8px; color:#64748b; font-size:12px;">{escape(citations)}</td>
            </tr>
            """
        )

    findings_table = f"""
    <section style="margin-top:16px;">
      <h2 style="font-size:18px; color:#0f172a;">Findings ({len(audit.findings)})</h2>
      <table style="width:100%; border-collapse:collapse; margin-top:8px; font-size:14px;">
        <thead style="background:#f1f5f9; color:#0f172a;">
          <tr>
            <th style="text-align:left; padding:8px;">Severity</th>
            <th style="text-align:left; padding:8px;">Rule ID</th>
            <th style="text-align:left; padding:8px;">Rule Type</th>
            <th style="text-align:left; padding:8px;">Category</th>
            <th style="text-align:left; padding:8px;">Summary</th>
            <th style="text-align:left; padding:8px;">Fields</th>
            <th style="text-align:left; padding:8px;">Message</th>
            <th style="text-align:left; padding:8px;">Citations</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows) if rows else '<tr><td colspan="8" style="padding:8px; color:#64748b;">No findings.</td></tr>'}
        </tbody>
      </table>
    </section>
    """

    doc_meta = audit.document_metadata
    meta_section = f"""
    <section style="margin-top:16px; padding:12px; background:#fff; border:1px solid #e2e8f0; border-radius:8px;">
      <h2 style="margin:0 0 8px 0; font-size:18px; color:#0f172a;">Document</h2>
      <p style="margin:4px 0; color:#334155;">Filename: {escape(doc_meta.filename or 'N/A')}</p>
      <p style="margin:4px 0; color:#334155;">Content type: {escape(doc_meta.content_type or 'unknown')}</p>
      <p style="margin:4px 0; color:#334155;">Source: {escape(doc_meta.source or '')}</p>
    </section>
    """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="UTF-8" />
        <title>Audit Report</title>
      </head>
      <body style="font-family:Arial, sans-serif; margin:24px; background:#f8fafc;">
        {header}
        {meta_section}
        {summary_section}
        {findings_table}
      </body>
    </html>
    """

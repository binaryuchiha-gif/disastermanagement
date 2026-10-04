"""Minimal publication-quality SVG plotting (pure stdlib, no matplotlib).

Supports grouped bar charts with error bars, line/scatter curves, and
calibration plots. Output is a standalone .svg string. Deliberately simple but
clean (axes, ticks, labels, legend). Used because matplotlib cannot be installed
in the sandbox; the figures regenerate identically with `make figures`.
"""

from __future__ import annotations

import html
import math

_PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf"]


def _esc(s: str) -> str:
    return html.escape(str(s))


class SVG:
    def __init__(self, width=720, height=440, title="", subtitle=""):
        self.w = width
        self.h = height
        self.title = title
        self.subtitle = subtitle
        self.parts: list[str] = []
        # plot area margins
        self.ml, self.mr, self.mt, self.mb = 70, 150, 60, 70
        self.px0 = self.ml
        self.py0 = self.h - self.mb
        self.pw = self.w - self.ml - self.mr
        self.ph = self.h - self.mt - self.mb

    def _x(self, frac):
        return self.px0 + frac * self.pw

    def _y(self, frac):
        return self.py0 - frac * self.ph

    def axes(self, xlabel, ylabel, xmin, xmax, ymin, ymax, xticks=5, yticks=5):
        self._xmin, self._xmax = xmin, xmax
        self._ymin, self._ymax = ymin, ymax
        p = self.parts
        # frame
        p.append(f'<rect x="{self.px0}" y="{self.mt}" width="{self.pw}" '
                 f'height="{self.ph}" fill="#fafafa" stroke="#ccc"/>')
        for i in range(yticks + 1):
            frac = i / yticks
            y = self._y(frac)
            val = ymin + frac * (ymax - ymin)
            p.append(f'<line x1="{self.px0}" y1="{y:.1f}" x2="{self.px0+self.pw}" '
                     f'y2="{y:.1f}" stroke="#e5e5e5"/>')
            p.append(f'<text x="{self.px0-8}" y="{y+4:.1f}" font-size="11" '
                     f'text-anchor="end" fill="#333">{val:.3g}</text>')
        for i in range(xticks + 1):
            frac = i / xticks
            x = self._x(frac)
            val = xmin + frac * (xmax - xmin)
            p.append(f'<text x="{x:.1f}" y="{self.py0+18}" font-size="11" '
                     f'text-anchor="middle" fill="#333">{val:.3g}</text>')
        p.append(f'<text x="{self.px0+self.pw/2:.1f}" y="{self.h-20}" '
                 f'font-size="13" text-anchor="middle">{_esc(xlabel)}</text>')
        p.append(f'<text x="22" y="{self.mt+self.ph/2:.1f}" font-size="13" '
                 f'text-anchor="middle" transform="rotate(-90 22 {self.mt+self.ph/2:.1f})">'
                 f'{_esc(ylabel)}</text>')

    def _fx(self, v):
        return (v - self._xmin) / (self._xmax - self._xmin + 1e-12)

    def _fy(self, v):
        return (v - self._ymin) / (self._ymax - self._ymin + 1e-12)

    def line(self, xs, ys, color_idx=0, label="", dash="", markers=True):
        c = _PALETTE[color_idx % len(_PALETTE)]
        pts = " ".join(f"{self._x(self._fx(x)):.1f},{self._y(self._fy(y)):.1f}"
                       for x, y in zip(xs, ys))
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<polyline points="{pts}" fill="none" stroke="{c}" '
                          f'stroke-width="2"{d}/>')
        if markers:
            for x, y in zip(xs, ys):
                self.parts.append(f'<circle cx="{self._x(self._fx(x)):.1f}" '
                                  f'cy="{self._y(self._fy(y)):.1f}" r="3" fill="{c}"/>')
        if label:
            self._legend(label, c)

    def bars(self, groups, series, color_idx_base=0):
        """groups: list of group labels. series: list of (name, values, errors)."""
        n_groups = len(groups)
        n_series = len(series)
        gw = self.pw / max(1, n_groups)
        bw = gw * 0.8 / max(1, n_series)
        for si, (name, vals, errs) in enumerate(series):
            c = _PALETTE[(color_idx_base + si) % len(_PALETTE)]
            for gi, v in enumerate(vals):
                x = self.px0 + gi * gw + gw * 0.1 + si * bw
                y = self._y(self._fy(v))
                hgt = self.py0 - y
                self.parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw*0.9:.1f}" '
                                  f'height="{max(0,hgt):.1f}" fill="{c}" opacity="0.85"/>')
                if errs and gi < len(errs) and errs[gi] > 0:
                    e = errs[gi]
                    ytop = self._y(self._fy(v + e))
                    ybot = self._y(self._fy(max(self._ymin, v - e)))
                    cx = x + bw * 0.45
                    self.parts.append(f'<line x1="{cx:.1f}" y1="{ytop:.1f}" '
                                      f'x2="{cx:.1f}" y2="{ybot:.1f}" stroke="#222"/>')
                    self.parts.append(f'<line x1="{cx-3:.1f}" y1="{ytop:.1f}" '
                                      f'x2="{cx+3:.1f}" y2="{ytop:.1f}" stroke="#222"/>')
            self._legend(name, c)
        for gi, g in enumerate(groups):
            x = self.px0 + gi * gw + gw / 2
            self.parts.append(f'<text x="{x:.1f}" y="{self.py0+18}" font-size="11" '
                              f'text-anchor="middle">{_esc(g)}</text>')

    _legend_i = 0

    def _legend(self, label, color):
        y = self.mt + 10 + self._legend_i * 20
        x = self.px0 + self.pw + 15
        self.parts.append(f'<rect x="{x}" y="{y-9}" width="12" height="12" fill="{color}"/>')
        self.parts.append(f'<text x="{x+18}" y="{y+1}" font-size="11">{_esc(label)}</text>')
        self._legend_i += 1

    def render(self) -> str:
        head = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" '
                f'height="{self.h}" font-family="sans-serif">']
        head.append(f'<rect width="{self.w}" height="{self.h}" fill="white"/>')
        if self.title:
            head.append(f'<text x="{self.w/2}" y="26" font-size="16" '
                        f'font-weight="bold" text-anchor="middle">{_esc(self.title)}</text>')
        if self.subtitle:
            head.append(f'<text x="{self.w/2}" y="44" font-size="12" fill="#b00" '
                        f'text-anchor="middle">{_esc(self.subtitle)}</text>')
        return "\n".join(head + self.parts + ["</svg>"])

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.render())

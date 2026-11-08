import type { ReactNode } from 'react'

export function BrandMark({ badge }: { badge?: ReactNode }) {
  return (
    <span className="brand-mark">
      <img
        className="brand-logo"
        src="/brand/docnelo/docnelo-horizontal-dark-transparent.png"
        alt="Docnelo"
        height={28}
        loading="eager"
      />
      {badge ? <span className="brand-badge">{badge}</span> : null}
    </span>
  )
}
import { useEffect, useState } from "react"
import { Link, useLocation } from "react-router-dom"
import { ArrowRight, Flag, Info } from "lucide-react"
import { ThemeToggle } from "@/components/theme-toggle"
import { CopyPicks, SavedPickList } from "./card-page"
import { quoteDate } from "./quote-display"
import { decodeSharedCard, formatSharedPicksText, type SharedCard } from "./shared-card"
import "./matchup-desk.css"

export default function SharedCardPage() {
  const { hash } = useLocation()
  const [state, setState] = useState<{ hash: string; card?: SharedCard; error?: string }>({ hash: "" })
  const current = state.hash === hash ? state : null
  useEffect(() => {
    document.title = "Shared picks · Golf Model"
    let cancelled = false
    async function read() {
      try {
        if (hash.length > 70_000) throw new Error("This share link is too large.")
        const params = new URLSearchParams(hash.slice(1))
        if (params.size !== 1 || !params.get("card")) throw new Error("This share link is incomplete.")
        const card = await decodeSharedCard(params.get("card")!)
        if (!cancelled) setState({ hash, card })
      } catch {
        if (!cancelled) setState({ hash, error: "This link is incomplete or unsupported. Ask the sender for a new share link." })
      }
    }
    void read()
    return () => { cancelled = true }
  }, [hash])
  return <div className="matchup-desk md-shared-page">
    <a className="md-skip" href="#shared-picks" onClick={event => { event.preventDefault(); document.getElementById("shared-picks")?.focus() }}>Skip to picks</a>
    <header className="md-masthead"><Link className="md-brand" to="/" aria-label="Golf Model home"><Flag size={24} /><span>GOLF<span>MODEL</span></span></Link><nav aria-label="Main navigation"><Link to="/">Markets</Link><Link to="/card">My card</Link></nav><div className="md-header-tools"><ThemeToggle /></div></header>
    <main id="shared-picks" className="md-main" tabIndex={-1}><section className="md-single-page">
      <div className="md-section-title"><div><h1>Shared picks.</h1><p>{current?.card ? `${current.card.picks.length} ${current.card.picks.length === 1 ? "selection" : "selections"} · Shared ${quoteDate(current.card.createdAt)}` : "A saved card from Golf Model."}</p></div>{current?.card && <CopyPicks getText={() => formatSharedPicksText(current.card!)} />}</div>
      {!current ? <div className="md-board-empty" role="status"><h2>Opening the card…</h2></div> : current.error ? <div className="md-board-empty" role="alert"><Info size={30} /><h2>This card couldn’t open.</h2><p>{current.error}</p><Link className="md-button" to="/">Explore markets <ArrowRight size={16} /></Link></div> : current.card ? <><p className="md-card-notice"><Info size={16} />Shared snapshot · prices may have moved. Selections are unverified; no placed bets are confirmed.</p><SavedPickList picks={current.card.picks} /></> : null}
    </section></main>
    <footer className="md-footer"><span>Golf Model</span><span>Original quotes. Shared as saved.</span><Link to="/">Explore markets <ArrowRight size={13} /></Link></footer>
  </div>
}

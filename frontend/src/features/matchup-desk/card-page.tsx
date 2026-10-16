import { useState } from "react"
import { Link } from "react-router-dom"
import { ArrowRight, Bookmark, Clock3, Copy, Download, Info, Share2, Trash2, X } from "lucide-react"
import { formatEdge, formatPrice, formatProbability, MARKET_LABELS, type SavedPick } from "./market-rows"
import { createSharedCard, encodeSharedCard, formatSharedPicksText, MAX_SHARED_PICKS } from "./shared-card"

import { quoteDate, bookLabel } from "./quote-display"

export function SavedPickList({ picks, remove }: { picks: SavedPick[]; remove?: (id: string) => void }) {
  return <div className="md-saved-list">{picks.map(row => <article key={row.id} className="md-saved-pick">
    {remove && <div className="md-saved-top"><button aria-label={`Remove ${row.player} from card`} onClick={() => remove(row.id)}><Trash2 size={16} /></button></div>}
    <div className="md-saved-main">
      <div><h2>{row.player}</h2><p>{row.opponent ? `vs ${row.opponent}` : row.marketType}</p></div>
      <div><strong>{formatPrice(row.odds)}</strong><span>{bookLabel(row.book)}</span></div>
      <div><strong>{formatProbability(row.probability)}</strong><span>Model win</span></div>
      <div><strong className={row.ev !== null && row.ev > 0 ? "md-positive" : ""}>{formatEdge(row.ev)}</strong><span>Model EV</span></div>
    </div>
    <p className="md-saved-event">{row.eventName} · {MARKET_LABELS[row.market]}{row.round ? ` · Round ${row.round}` : ""}</p>
    <p>{row.reason || "No additional explanation was attached to this prediction."}</p>
    <div className="md-saved-foot"><span><Clock3 size={13} />{row.lineAt ? "Price" : "Snapshot"} · {quoteDate(row.lineAt || row.snapshotAt)}</span><span>Saved quote · current price unverified</span></div>
    <details className="md-quote-record"><summary>Quote record</summary><dl><div><dt>Snapshot</dt><dd>{quoteDate(row.snapshotAt)}</dd></div><div><dt>Saved</dt><dd>{quoteDate(row.savedAt)}</dd></div><div><dt>Market</dt><dd>{row.marketType}</dd></div><div><dt>Event ID</dt><dd>{row.eventId}</dd></div></dl></details>
  </article>)}</div>
}

export function CopyPicks({ getText }: { getText: () => string }) {
  const [message, setMessage] = useState("")
  const [manual, setManual] = useState("")
  async function copy() {
    let value = ""
    try {
      value = getText()
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable")
      await navigator.clipboard.writeText(value)
      setManual("")
      setMessage("Picks copied.")
    } catch (error) {
      setManual(value)
      setMessage(value ? "Select and copy the picks below." : error instanceof Error ? error.message : "These picks could not be copied.")
    }
  }
  return <div className="md-copy-picks"><button className="md-button" onClick={() => void copy()}><Copy size={16} />Copy picks</button>{message && <p role="status">{message}</p>}{manual && <textarea aria-label="Picks to copy" readOnly value={manual} rows={10} onFocus={event => event.currentTarget.select()} />}</div>
}

function ShareCard({ card, close }: { card: SavedPick[]; close: () => void }) {
  const [selected, setSelected] = useState(() => new Set(card.map(pick => pick.id)))
  const [link, setLink] = useState("")
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")
  const picks = card.filter(pick => selected.has(pick.id))
  const valid = picks.length > 0 && picks.length <= MAX_SHARED_PICKS
  async function createLink() {
    setBusy(true)
    setMessage("")
    try {
      const token = await encodeSharedCard(createSharedCard(picks))
      setLink(`${window.location.origin}/shared-card#card=${token}`)
      setMessage("Link ready.")
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The share link could not be created. Try fewer picks.")
    } finally { setBusy(false) }
  }
  async function copyLink() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable")
      await navigator.clipboard.writeText(link)
      setMessage("Link copied.")
    } catch { setMessage("Select and copy the link below.") }
  }
  return <section className="md-share-composer" aria-labelledby="share-heading">
    <div className="md-subsection-heading"><h2 id="share-heading">Choose picks to share.</h2><button className="md-button" aria-label="Close sharing" onClick={close}><X size={16} /></button></div>
    <p>Share the selected picks at their saved prices.</p>
    <fieldset disabled={busy}><legend className="md-sr-only">Picks to share</legend><div className="md-share-choices">{card.map(pick => <label key={pick.id}>
      <input type="checkbox" checked={selected.has(pick.id)} onChange={() => { const next = new Set(selected); if (next.has(pick.id)) next.delete(pick.id); else next.add(pick.id); setSelected(next); setLink(""); setMessage("") }} />
      <span><strong>{pick.player}{pick.opponent ? ` vs ${pick.opponent}` : ""}</strong><small>{pick.eventName} · {MARKET_LABELS[pick.market]}{pick.round ? ` · R${pick.round}` : ""}</small></span><span>{formatPrice(pick.odds)}<small>{bookLabel(pick.book)}</small></span>
    </label>)}</div></fieldset>
    <div className="md-share-actions"><span>{picks.length} selected{picks.length > MAX_SHARED_PICKS ? ` · Choose up to ${MAX_SHARED_PICKS}` : ""}</span><button className="md-button md-button-primary" disabled={!valid || busy} onClick={() => void createLink()}><Share2 size={16} />{busy ? "Creating link…" : "Create share link"}</button>{valid && <CopyPicks key={JSON.stringify(picks.map(pick => pick.id))} getText={() => formatSharedPicksText(createSharedCard(picks))} />}</div>
    {link && <div className="md-share-link"><label htmlFor="shared-card-link">Share link</label><div><input id="shared-card-link" readOnly value={link} onFocus={event => event.currentTarget.select()} /><button className="md-button" onClick={() => void copyLink()}><Copy size={16} />Copy link</button></div><a className="md-text-link" href={link} target="_blank" rel="noopener noreferrer">Preview shared card <ArrowRight size={16} /></a><p>Anyone with this link can read these picks. It won’t update when your card changes.</p></div>}
    {message && <p className="md-share-message" role="status">{message}</p>}
  </section>
}

export function CardPage({ card, remove, marketSearch }: { card: SavedPick[]; remove: (id: string) => void; marketSearch: string }) {
  const [exported, setExported] = useState(false)
  const [sharing, setSharing] = useState(false)
  function exportCard() {
    const lines = ["event,market,round,player,opponent,book,odds,model_probability,model_ev,quote_time,snapshot_time,saved_time,quote_id,event_id,reason,implied_probability", ...card.map(row => [row.eventName, row.marketType, row.round, row.player, row.opponent, row.book, row.odds, row.probability ?? "", row.ev ?? "", row.lineAt ?? "", row.snapshotAt ?? "", row.savedAt, row.id, row.eventId, row.reason, row.impliedProbability ?? ""].map(value => `"${String(value).replaceAll('"', '""')}"`).join(","))]
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" }))
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = `golf-card-${new Date().toISOString().slice(0, 10)}.csv`
    anchor.click()
    URL.revokeObjectURL(url)
    setExported(true)
  }
  return <section className="md-single-page">
    <div className="md-section-title"><div><h1>Your card.</h1><p>Build your own card. Share the picks you want others to see.</p></div>{card.length > 0 && <div className="md-card-actions"><button className="md-button md-button-primary" onClick={() => setSharing(!sharing)} aria-expanded={sharing}><Share2 size={16} />Share picks</button><button className="md-button" onClick={exportCard}><Download size={16} />{exported ? "Export again" : "Export card"}</button></div>}</div>
    <p className="md-card-notice"><Info size={16} />Stored in this browser. These are saved research selections; no bets have been placed.</p>
    {sharing && card.length > 0 && <ShareCard key={JSON.stringify(card.map(p => p.id))} card={card} close={() => setSharing(false)} />}
    {!card.length ? <div className="md-card-empty"><Bookmark size={38} /><h2>A considered card starts here.</h2><p>Save a matchup from the board to keep its price, probability and reasoning together.</p><Link className="md-button md-button-primary" to={`/markets${marketSearch}`}>Explore matchups <ArrowRight size={16} /></Link></div> : !sharing && <SavedPickList picks={card} remove={remove} />}
  </section>
}

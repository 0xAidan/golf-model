import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link, NavLink, useLocation, useSearchParams } from "react-router-dom"
import { ArrowDown, ArrowRight, ArrowUp, ArrowUpRight, Bookmark, ChartNoAxesCombined, ChevronRight, CircleHelp, Flag, FlaskConical, History, ListOrdered, RefreshCw, Search, Settings2, ShieldCheck, SlidersHorizontal } from "lucide-react"
import { ThemeToggle } from "@/components/theme-toggle"
import { getDeskBoard, type OperatorBoard } from "@/features/operator-data/operator-api"
import { MatchupDesk } from "@/features/matchup-desk/matchup-desk"
import { number, shortDate, signed } from "./charts"
import { currentProjectionMatchesSnapshot, loadLearning } from "./learning-report"
import "./learning-workspace.css"

const PerformancePage = lazy(() => import("./performance-page"))
const ModelsPage = lazy(() => import("./models-page"))
const mainLinks = [
  { to: "/", label: "Rankings", Icon: ListOrdered },
  { to: "/markets", label: "Markets", Icon: SlidersHorizontal },
  { to: "/performance", label: "Performance", Icon: ChartNoAxesCombined },
  { to: "/models", label: "Models", Icon: FlaskConical },
]

export function LearningWorkspace() {
  const location = useLocation()
  const route = location.pathname
  const rankings = route === "/" || route === "/rankings"
  const desk = ["/markets", "/card", "/evidence"].includes(route)
  const title = rankings ? "Rankings" : route === "/models" ? "Models" : route === "/performance" ? "Performance" : route === "/card" ? "My card" : route === "/evidence" ? "History" : "Markets"
  useEffect(() => { document.title = `${title} · Golf Model` }, [title])
  return <div className="learning-workspace">
    <a className="lw-skip" href={desk ? "#desk-main" : "#workspace-main"}>Skip to content</a>
    <aside className="lw-rail">
      <Link to="/" className="lw-brand" aria-label="Golf Model home"><span className="lw-brand-mark"><Flag size={23}/></span><span>golf<span>model</span></span></Link>
      <nav aria-label="Main navigation">{mainLinks.map(({to,label,Icon}) => <NavLink key={to} to={to} end={to === "/"} className={({isActive}) => isActive || (rankings && to === "/") ? "is-active" : ""}><Icon size={18}/><span>{label}</span>{((rankings && to === "/") || route === to) && <ChevronRight size={15} className="lw-nav-arrow"/>}</NavLink>)}</nav>
      <div className="lw-rail-secondary"><Link to="/card"><Bookmark size={17}/>My card</Link><Link to="/evidence"><History size={17}/>Season archive</Link><Link to="/players"><Search size={17}/>Player research</Link></div>
      <div className="lw-rail-bottom"><Link to="/models?view=baseline"><span className="lw-status-dot"/>Original model preserved<ArrowUpRight size={14}/></Link><div><Link to="/system" aria-label="System status"><Settings2 size={17}/></Link><span>Made for the long game.</span></div></div>
    </aside>
    <div className="lw-workarea">
      <header className="lw-topbar"><div><span>Workspace</span><ChevronRight size={13}/><strong>{title}</strong></div><div><Link to="/evidence">2026 season<ArrowUpRight size={13}/></Link><ThemeToggle/></div></header>
      {desk ? <MatchupDesk embedded/> : <main id="workspace-main" className={`lw-main ${rankings ? "lw-main-rankings" : ""}`}><Suspense fallback={<LoadingState label={`Opening ${title.toLowerCase()}…`}/>}>{rankings ? <RankingsPage/> : route === "/performance" ? <PerformancePage/> : <ModelsPage/>}</Suspense></main>}
    </div>
  </div>
}

export function LoadingState({label}: {label: string}) { return <div className="lw-loading" role="status"><span>{label}</span><div/><div/><div/><div/></div> }
export function ReportError({ retry, title = "This report is unavailable." }: { retry: () => void; title?: string }) { return <div className="lw-empty" role="alert"><CircleHelp size={28}/><h2>{title}</h2><p>Your original rankings and season archive are still available.</p><button className="lw-button" onClick={retry}><RefreshCw size={15}/>Try again</button></div> }

type Ranking = { key: string; name: string; rank: number; score: number | null; form: number | null; course: number | null; momentum: number | null; rounds: number | null; courseRounds: number | null; delta: number | null; sg: number | null; challengerRank: number | null }
const numeric = (v: unknown): number | null => typeof v === "number" && Number.isFinite(v) ? v : null
function verifiedField(board?: OperatorBoard): boolean {
  if (!board || board.eligibility?.verified !== true || !board.event?.event_id) return false
  const suppliedId = board.eligibility.field_event_id
  return suppliedId == null || String(suppliedId) === String(board.event.event_id)
}
function normalizeRankings(board?: OperatorBoard): Ranking[] {
  if (!board || !verifiedField(board) || ["unavailable", "error"].includes(board.state) || !Array.isArray(board.rankings)) return []
  return board.rankings.filter(r => !!r && typeof r === "object").map((r,i) => {
    const availability = r.availability as Record<string, unknown> | undefined
    return { key: String(r.player_key || r.player || i), name: String(r.player || r.player_display || r.player_key || "Unknown player"), rank: numeric(r.rank) ?? i + 1, score: numeric(r.composite ?? r.composite_score), form: numeric(r.form), course: numeric(r.course_fit), momentum: numeric(r.momentum), rounds: numeric(availability?.recent_rounds_count), courseRounds: numeric(r.course_rounds), delta: numeric(r.rank_delta), sg: null, challengerRank: null }
  })
}
function FieldDistribution({rows, selected, research}: {rows: Ranking[]; selected: Ranking; research: boolean}) {
  const value = (row: Ranking) => research ? row.sg : row.score
  const values = rows.map(value).filter((v):v is number => v !== null)
  const lo = research ? Math.min(...values, 0) : 0, hi = research ? Math.max(...values, 0) : 100
  const x = (v: number) => 12 + (v - lo) / (hi - lo || 1) * 256
  const score = value(selected)
  const unit = research ? "expected SG per round" : "composite score"
  return <div className="lw-field-distribution"><svg viewBox="0 0 280 64" role="img" aria-label={`${selected.name}'s ${unit} ${number(score)} compared with ${values.length} field projections.`}><line x1="12" x2="268" y1="35" y2="35" className="lw-chart-grid"/>{rows.filter(r => value(r) !== null).map((r, i) => <circle key={r.key} cx={x(value(r)!)} cy={35 - (i % 4) * 5} r="2" className={r.key === selected.key ? "is-selected" : "lw-field-dot"}/>)}{score !== null && <><line x1={x(score)} x2={x(score)} y1="8" y2="42" className="lw-selected-guide"/><circle cx={x(score)} cy="10" r="4" className="is-selected"/></>}<text x="12" y="61">{number(lo, research ? 1 : 0)}</text><text x="268" y="61" textAnchor="end">{number(hi, research ? 1 : 0)}</text></svg><span>Position in the field · {unit}</span></div>
}

function useCompactLayout() {
  const [compact, setCompact] = useState(() => typeof window.matchMedia === "function" && window.matchMedia("(max-width: 1050px)").matches)
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return
    const media = window.matchMedia("(max-width: 1050px)")
    const update = () => setCompact(media.matches)
    update()
    media.addEventListener("change", update)
    return () => media.removeEventListener("change", update)
  }, [])
  return compact
}

function RankingsPage() {
  const [params,setParams] = useSearchParams()
  const mode = params.get("mode") === "live" ? "live" : "upcoming"
  const [search,setSearch] = useState("")
  const [selectedKey,setSelectedKey] = useState<string | null>(null)
  const [sort,setSort] = useState<{key: "rank" | "score" | "form" | "course" | "momentum"; asc: boolean}>({key:"rank",asc:true})
  const [view,setView] = useState("baseline")
  const compact = useCompactLayout()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const insightRef = useRef<HTMLElement>(null)
  const insightToggleRef = useRef<HTMLButtonElement>(null)
  const compactSummaryRef = useRef<HTMLButtonElement>(null)
  const selectedButton = useRef<HTMLButtonElement | null>(null)
  const selectPlayer = (key: string, button: HTMLButtonElement) => {
    setSelectedKey(key)
    selectedButton.current = button
    if (compact) {
      setDetailsOpen(true)
      requestAnimationFrame(() => {
        insightToggleRef.current?.focus({ preventScroll: true })
        insightRef.current?.scrollIntoView?.({ block: "start", behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" })
      })
    }
  }
  const toggleDetails = () => {
    setDetailsOpen(open => !open)
    if (detailsOpen) {
      const target = selectedButton.current ?? compactSummaryRef.current
      target?.focus({ preventScroll: true })
      target?.scrollIntoView?.({ block: "center", behavior: "auto" })
    }
  }
  const board = useQuery({queryKey:["matchup-desk",mode],queryFn:({signal})=>getDeskBoard({track:"champion",mode},signal),staleTime:30_000,refetchInterval:60_000,retry:false})
  const learning = useQuery({queryKey:["learning-report"],queryFn:({signal})=>loadLearning(signal),staleTime:300_000,retry:false})
  const baseline = useMemo(()=>normalizeRankings(board.data),[board.data])
  const evaluated = learning.data?.state === "insufficient_data" ? undefined : learning.data
  const learnedEvent = evaluated?.current_event
  const challenger = useMemo(()=>new Map((evaluated?.current_rankings || []).map(r=>[r.player_key,r])),[evaluated])
  const forward = evaluated?.forward_candidate
  const currentModelMatches = evaluated?.schema_version === 1 || (!!forward && forward.evaluated_hash === evaluated?.candidate.hash && evaluated?.current_rankings_model_hash === forward.hash)
  const candidateAvailable = currentModelMatches && currentProjectionMatchesSnapshot(evaluated, board.data) && !learning.isError && !board.isError && baseline.some(r => challenger.has(r.key)) && mode === "upcoming" && !!learnedEvent?.event_id && String(learnedEvent.event_id) === String(board.data?.event?.event_id)
  const effectiveView = candidateAvailable ? view : "baseline"
  const rows = useMemo(()=>baseline.map(r=>({...r, sg: candidateAvailable ? challenger.get(r.key)?.expected_sg_per_round ?? null : null, challengerRank: candidateAvailable ? challenger.get(r.key)?.rank ?? null : null})),[baseline,challenger,candidateAvailable])
  const filtered = useMemo(()=>rows.filter(r=>r.name.toLowerCase().includes(search.toLowerCase())).sort((a,b)=> {
    const val = (r: Ranking) => effectiveView === "challenger" && sort.key === "rank" ? r.challengerRank : effectiveView === "challenger" && sort.key === "score" ? r.sg : r[sort.key]
    const va=val(a), vb=val(b); if(va === null)return 1;if(vb === null)return -1;return (va-vb)*(sort.asc?1:-1)
  }),[rows,search,sort,effectiveView])
  const selected = rows.find(r=>r.key===selectedKey) || filtered[0]
  const isResearch = effectiveView === "challenger"
  const projectedCount = rows.filter(r => r.sg !== null).length
  const setMode = (next: string) => {const p = new URLSearchParams(params);p.set("mode",next);setParams(p);setSelectedKey(null);setDetailsOpen(false);setView("baseline")}
  const changeSort = (key: typeof sort.key) => setSort(s=>({key,asc:s.key===key?!s.asc:key==="rank"}))
  return <>
    <div className="lw-page-heading lw-rankings-heading"><h1>Rankings</h1><Link className="lw-button lw-primary" to={`/markets?mode=${mode}`}>Explore markets<ArrowUpRight size={16}/></Link></div>
    <section className="lw-event-heading" aria-label="Current event"><div><span className="lw-event-emblem"><Flag size={20}/></span><div><h2>{board.data?.event?.event_name || (board.isLoading ? "Reading the field…" : "Event unavailable")}</h2><p>{board.data?.event?.course_name || "Course not published"}{rows.length ? ` · ${rows.length} players` : ""}</p>{board.data?.source?.generated_at && <p className={`lw-event-source ${board.data.state !== "fresh" ? "is-older" : ""}`}>{shortDate(board.data.source.generated_at)} · {board.data.state === "fresh" ? "Published" : "Older source snapshot"}</p>}</div></div><div className="lw-event-tools"><div className="lw-segmented" aria-label="Event context">{["upcoming","live"].map(v=><button key={v} aria-pressed={mode===v} onClick={()=>setMode(v)}>{v==="live"?"In play":"Upcoming"}</button>)}</div><button className="lw-icon-button" aria-label="Reload rankings" disabled={board.isFetching} onClick={()=>void board.refetch()}><RefreshCw size={16}/></button></div></section>
    {verifiedField(board.data) && <details className="lw-field-verification"><summary><ShieldCheck size={14}/>Field membership verified<ChevronRight size={12}/></summary><p>Event field verified{numeric(board.data?.eligibility.field_player_count) !== null ? ` · ${board.data?.eligibility.field_player_count} confirmed players` : ""}. This verifies field membership, not prices or model accuracy.</p></details>}
    <div className="lw-rankings-layout">    <aside ref={insightRef} className="lw-player-aside" data-empty={!selected} hidden={compact && !detailsOpen} aria-label="Selected player details">
      {compact && detailsOpen && selected && <button ref={insightToggleRef} className="lw-mobile-insight-toggle" aria-expanded={detailsOpen} aria-controls="selected-player-content" onClick={toggleDetails}><span>Back to rankings</span><span>Close details<ChevronRight size={15}/></span></button>}
      <div id="selected-player-content" className="lw-player-content" hidden={compact && !detailsOpen}>{selected ? <>
      <div className="lw-player-name"><h2>{selected.name}</h2><Link aria-label={`Open ${selected.name} profile`} to={`/players/${encodeURIComponent(selected.key)}`}><ArrowUpRight size={18}/></Link></div><div className="lw-player-score"><strong>{isResearch?signed(selected.sg,"",2):number(selected.score)}</strong><span>{isResearch?"Expected SG / round":"Composite score"}<small>#{isResearch?(selected.challengerRank??"—"):selected.rank} in this field</small></span></div>
      <FieldDistribution rows={rows} selected={selected} research={isResearch}/><div className="lw-component-heading"><h3>Behind the ranking</h3><span>Original model · /100</span></div><div className="lw-component-bars">{[{name:"Form",v:selected.form},{name:"Course fit",v:selected.course},{name:"Momentum",v:selected.momentum}].map(c=><div key={c.name}><div><span>{c.name}</span><strong>{number(c.v)}</strong></div><div className="lw-component-track"><i style={{width:`${Math.max(0,Math.min(100,c.v??0))}%`}}/></div></div>)}</div>
      <div className="lw-player-coverage"><span>Recent rounds<strong>{selected.rounds??"—"}</strong></span><span>Course rounds<strong>{selected.courseRounds??"—"}</strong></span></div>{selected.courseRounds === 0 && <p className="lw-muted lw-small">No course rounds in this snapshot. Course fit includes modeled estimates.</p>}
      <Link className="lw-button lw-primary" to={`/markets?mode=${mode}&q=${encodeURIComponent(selected.name)}`}>Find {selected.name.split(" ").at(-1)} markets<ArrowRight size={15}/></Link><Link className="lw-plain-link" to={`/players/${encodeURIComponent(selected.key)}`}>Full player profile<ArrowUpRight size={14}/></Link>
    </> : <><h2>Every rank has a reason.</h2><p className="lw-muted">Select a player to inspect form, course fit and momentum.</p></>}
    <div className="lw-learning-note"><FlaskConical size={18}/><div><strong>A model that earns its place.</strong><p>Challengers learn from past rounds. Later events measure what improved.</p><Link to="/models">See model development<ArrowRight size={14}/></Link></div></div></div></aside>
    <section className="lw-field-panel" aria-label="Full field rankings"><div className="lw-section-header"><div><h2>Field rankings <span>{rows.length || "—"}</span></h2><p>{isResearch ? "Learned strokes-gained projection · research" : "Original model · published composite"}</p></div><label className="lw-model-select"><span className="lw-sr-only">Ranking model</span><select value={effectiveView} onChange={e=>setView(e.target.value)}><option value="baseline">Original model</option><option value="challenger" disabled={!candidateAvailable}>SG challenger{!candidateAvailable ? " · no matching field" : ""}</option></select></label></div>
      <label className="lw-search"><Search size={17}/><input aria-label="Search the field" placeholder="Find a player…" value={search} onChange={e=>setSearch(e.target.value)}/><span>{filtered.length} players</span></label>
      {compact && selected && <button ref={compactSummaryRef} className="lw-compact-selection" aria-label={`View ${selected.name} details`} aria-expanded={detailsOpen} aria-controls="selected-player-content" onClick={() => selectPlayer(selected.key, compactSummaryRef.current!)}><strong>{selected.name}</strong><span>View details<ChevronRight size={14}/></span></button>}
      {board.isLoading ? <LoadingState label="Loading the published rankings…"/> : board.isError ? <ReportError title="Rankings could not be loaded." retry={()=>void board.refetch()}/> : !rows.length ? <div className="lw-empty"><Flag size={30}/><h3>{board.data && !verifiedField(board.data) && board.data.state !== "empty" ? "The field needs verification." : mode==="live"?"No event is in play.":"The next field is not published yet."}</h3><p>{board.data?.reason?.message || "Rankings will appear when the source publishes a verified field."}</p>{mode==="live"&&<button className="lw-button" onClick={()=>setMode("upcoming")}>View upcoming field<ArrowRight size={15}/></button>}</div> : <>
        {isResearch && <p className="lw-notice">Shadow projection in expected SG per round. The original model's composite scores remain alongside it. {projectedCount} of {rows.length} players projected; others have no challenger forecast.{forward && <span> Forward refit through {shortDate(forward.trained_through)} · model {forward.hash.slice(0, 12)}.</span>}</p>}
        <div className="lw-table-scroll"><table className="lw-rankings-table"><thead><tr>{([{key:"rank",label:"Rank"},{key:null,label:"Player"},{key:"score",label:isResearch?"Exp. SG":"Score"},{key:"form",label:"Form"},{key:"course",label:"Course"},{key:"momentum",label:"Momentum"}] as const).map(c=><th key={c.label} className={c.key === "rank"?"lw-rank-column":undefined} aria-sort={c.key && sort.key===c.key ? sort.asc?"ascending":"descending":undefined}>{c.key ? <button onClick={()=>changeSort(c.key)}>{c.label}{sort.key===c.key && (sort.asc?<ArrowUp size={12}/>:<ArrowDown size={12}/>)}</button> : c.label}</th>)}</tr></thead><tbody>{filtered.map(row=><tr key={row.key} className={selected?.key===row.key?"is-selected":""}><td><span className="lw-rank-number">{isResearch ? row.challengerRank ?? "—" : row.rank}</span></td><th scope="row"><button className="lw-player-button" aria-pressed={selected?.key===row.key} onClick={event=>selectPlayer(row.key,event.currentTarget)}>{row.name}<ChevronRight size={14}/></button></th><td className="lw-score">{isResearch?signed(row.sg,"",2):number(row.score)}</td><td>{number(row.form)}</td><td>{number(row.course)}</td><td><span className="lw-momentum-cell"><span className="lw-mini-meter" aria-hidden="true"><i style={{width:`${Math.min(100,Math.max(0,row.momentum??0))}%`}}/></span>{number(row.momentum)}</span></td></tr>)}</tbody></table></div>
        {!filtered.length && <div className="lw-empty"><h3>No players match “{search}”.</h3><button className="lw-button" onClick={()=>setSearch("")}>Clear search</button></div>}
        <div className="lw-table-foot"><span>{filtered.length} of {rows.length} players</span><span>{shortDate(board.data?.source?.generated_at ?? undefined)} · {board.data?.state === "fresh"?"Published":"Snapshot"}</span></div>
      </>}
    </section>
</div>
    <p className="lw-source-note">Published rankings retain their original model and event context. Research projections are versioned separately.</p>
  </>
}

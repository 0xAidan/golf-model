/**
 * course-data.ts
 * Hole-by-hole data for courses used on the PGA Tour.
 * Each course has 18 holes with par, yardage, scoring avg, difficulty rank,
 * handicap, and an editorial note.
 *
 * SVG hole maps are generated procedurally from path descriptors.
 */

export type HoleData = {
  number: number
  name?: string          // some courses have hole names
  par: number
  yards: number
  hcp: number            // handicap / stroke index
  scoring_avg: number    // historical scoring average
  diff_rank: number      // difficulty rank 1-18 (1 = hardest)
  note: string           // editorial footnote
  /** Approximate SVG path descriptor for fairway routing */
  shape: HoleShape
}

export type HoleShape = {
  /** "straight" | "dogleg-left" | "dogleg-right" | "par3" | "par5-snake" */
  type: "straight" | "dogleg-left" | "dogleg-right" | "par3" | "par5-snake"
  /** rough has water? */
  water?: boolean
  /** bunkers: number 1-4 */
  bunkers?: number
}

export type CourseData = {
  course_key: string
  name: string
  location: string
  par: number
  yards: number
  notes?: string
  holes: HoleData[]
}

/* ─── Augusta National ──────────────────────────────────────────────── */
const AUGUSTA: CourseData = {
  course_key: "augusta_national",
  name: "Augusta National Golf Club",
  location: "Augusta, GA",
  par: 72, yards: 7510,
  notes: "Home of The Masters. Renowned for its fast bentgrass greens and azalea-lined fairways.",
  holes: [
    { number: 1,  name: "Tea Olive",       par: 4, yards: 445, hcp: 4,  scoring_avg: 4.24, diff_rank: 4,  note: "Slight dogleg right, plays uphill. Deep bunker at 317-yd carry.", shape: { type: "dogleg-right", bunkers: 2 } },
    { number: 2,  name: "Pink Dogwood",    par: 5, yards: 575, hcp: 14, scoring_avg: 4.72, diff_rank: 14, note: "Dogleg left, reachable in two. Site of Oosthuizen's double-eagle in 2012.", shape: { type: "dogleg-left", bunkers: 1 } },
    { number: 3,  name: "Flowering Peach", par: 4, yards: 350, hcp: 18, scoring_avg: 3.97, diff_rank: 18, note: "Shortest par 4. Big hitters can drive near the green.", shape: { type: "straight", bunkers: 1 } },
    { number: 4,  name: "Palm Tree",       par: 3, yards: 240, hcp: 9,  scoring_avg: 3.24, diff_rank: 7,  note: "Long par 3 over a valley. Deep bunkers front-left.", shape: { type: "par3", bunkers: 2 } },
    { number: 5,  name: "Magnolia",        par: 4, yards: 455, hcp: 6,  scoring_avg: 4.29, diff_rank: 6,  note: "Hidden fairway bunker at 260 yds punishes distance. Crowned green.", shape: { type: "straight", bunkers: 2 } },
    { number: 6,  name: "Juniper",         par: 3, yards: 180, hcp: 16, scoring_avg: 3.12, diff_rank: 16, note: "Downhill par 3 to a shallow green. Back bunker collects overhit shots.", shape: { type: "par3", bunkers: 1 } },
    { number: 7,  name: "Pampas",          par: 4, yards: 450, hcp: 2,  scoring_avg: 4.35, diff_rank: 2,  note: "Severely uphill approach to a small, well-bunkered green. 2nd hardest hole.", shape: { type: "dogleg-left", bunkers: 3 } },
    { number: 8,  name: "Yellow Jasmine",  par: 5, yards: 570, hcp: 10, scoring_avg: 4.81, diff_rank: 10, note: "Uphill par 5. Only 3 bunkers but mound and slope protect the green.", shape: { type: "dogleg-right", bunkers: 2 } },
    { number: 9,  name: "Carolina Cherry", par: 4, yards: 460, hcp: 8,  scoring_avg: 4.26, diff_rank: 8,  note: "Sharp dogleg left downhill. Approach over a wide bunker complex.", shape: { type: "dogleg-left", bunkers: 3 } },
    { number: 10, name: "Camellia",        par: 4, yards: 495, hcp: 1,  scoring_avg: 4.37, diff_rank: 1,  note: "Hardest hole. Severe downhill tee shot, approach blind to fast sloped green.", shape: { type: "dogleg-left", bunkers: 2 } },
    { number: 11, name: "White Dogwood",   par: 4, yards: 520, hcp: 3,  scoring_avg: 4.31, diff_rank: 3,  note: "Amen Corner starts. Pond left, bunker back right. Crowd favorite.", shape: { type: "straight", water: true, bunkers: 1 } },
    { number: 12, name: "Golden Bell",     par: 3, yards: 155, hcp: 17, scoring_avg: 3.28, diff_rank: 17, note: "Most famous par 3 in golf. Swirling wind is deceptive. Spieth's quad in 2016.", shape: { type: "par3", water: true, bunkers: 2 } },
    { number: 13, name: "Azalea",          par: 5, yards: 510, hcp: 15, scoring_avg: 4.69, diff_rank: 15, note: "Reachable par 5 to a well-bunkered green. Rae's Creek catches short approaches.", shape: { type: "dogleg-left", water: true, bunkers: 3 } },
    { number: 14, name: "Chinese Fir",     par: 4, yards: 440, hcp: 11, scoring_avg: 4.22, diff_rank: 11, note: "Bunkered approach to an undulating green with severe tiers.", shape: { type: "straight", bunkers: 2 } },
    { number: 15, name: "Firethorn",       par: 5, yards: 550, hcp: 13, scoring_avg: 4.70, diff_rank: 13, note: "Signature par 5. Pond fronts the green — eagle or wet. Gene Sarazen's double-eagle in 1935.", shape: { type: "dogleg-right", water: true, bunkers: 1 } },
    { number: 16, name: "Redbud",          par: 3, yards: 170, hcp: 12, scoring_avg: 3.18, diff_rank: 12, note: "Island green par 3. Sunday pins in the back-right corner are virtually inaccessible.", shape: { type: "par3", water: true, bunkers: 2 } },
    { number: 17, name: "Nandina",         par: 4, yards: 440, hcp: 5,  scoring_avg: 4.28, diff_rank: 5,  note: "Dogleg right to an elevated green. Eisenhower Tree (removed 2014) once dominated strategy.", shape: { type: "dogleg-right", bunkers: 2 } },
    { number: 18, name: "Holly",           par: 4, yards: 465, hcp: 7,  scoring_avg: 4.30, diff_rank: 7,  note: "Uphill to a bunkered green. Sarazen's plaque marks where the tradition began.", shape: { type: "straight", bunkers: 3 } },
  ],
}

/* ─── TPC Sawgrass (Players Championship) ──────────────────────────── */
const TPC_SAWGRASS: CourseData = {
  course_key: "tpc_sawgrass",
  name: "TPC Sawgrass",
  location: "Ponte Vedra Beach, FL",
  par: 72, yards: 7215,
  notes: "Permanent home of The Players Championship. Stadium course with island green at 17.",
  holes: [
    { number: 1,  par: 4, yards: 423, hcp: 11, scoring_avg: 4.12, diff_rank: 11, note: "Short opener. The fairway narrows at 270 yds; conservative play often pays.", shape: { type: "straight", bunkers: 2 } },
    { number: 2,  par: 5, yards: 532, hcp: 15, scoring_avg: 4.65, diff_rank: 15, note: "Reachable par 5 with water guarding the right side. Birdie opportunity.", shape: { type: "dogleg-left", water: true, bunkers: 1 } },
    { number: 3,  par: 3, yards: 177, hcp: 17, scoring_avg: 3.10, diff_rank: 17, note: "Short iron over a hazard. Green slopes severely front-to-back.", shape: { type: "par3", water: true, bunkers: 2 } },
    { number: 4,  par: 4, yards: 384, hcp: 13, scoring_avg: 4.08, diff_rank: 13, note: "Short par 4 with a risk-reward drive over the left corner.", shape: { type: "dogleg-left", bunkers: 2 } },
    { number: 5,  par: 4, yards: 466, hcp: 3,  scoring_avg: 4.30, diff_rank: 3,  note: "One of the toughest holes on tour. Long approach to a small fast green.", shape: { type: "straight", bunkers: 3 } },
    { number: 6,  par: 4, yards: 393, hcp: 9,  scoring_avg: 4.15, diff_rank: 9,  note: "Slight dogleg with water left and a narrow fairway.", shape: { type: "dogleg-right", water: true, bunkers: 1 } },
    { number: 7,  par: 4, yards: 442, hcp: 5,  scoring_avg: 4.25, diff_rank: 5,  note: "Tree-lined par 4 requiring precise driving. Tucked pin positions reward bold play.", shape: { type: "straight", bunkers: 2 } },
    { number: 8,  par: 3, yards: 219, hcp: 7,  scoring_avg: 3.22, diff_rank: 7,  note: "Long par 3 across a marsh. Wind off the water makes club selection crucial.", shape: { type: "par3", water: true, bunkers: 1 } },
    { number: 9,  par: 5, yards: 583, hcp: 1,  scoring_avg: 4.87, diff_rank: 1,  note: "Hardest hole. Long dogleg right with water running the full left side.", shape: { type: "dogleg-right", water: true, bunkers: 2 } },
    { number: 10, par: 4, yards: 424, hcp: 12, scoring_avg: 4.14, diff_rank: 12, note: "Risk-reward off the tee with water left. Opens the back nine nicely.", shape: { type: "dogleg-left", water: true, bunkers: 1 } },
    { number: 11, par: 5, yards: 558, hcp: 14, scoring_avg: 4.60, diff_rank: 14, note: "Par 5 with water along the full right side. Key birdie/eagle chance.", shape: { type: "straight", water: true, bunkers: 2 } },
    { number: 12, par: 4, yards: 358, hcp: 16, scoring_avg: 4.05, diff_rank: 16, note: "Short par 4 where aggressive drivers try to reach or carry the trees.", shape: { type: "dogleg-right", bunkers: 2 } },
    { number: 13, par: 3, yards: 181, hcp: 18, scoring_avg: 3.08, diff_rank: 18, note: "Back-to-front sloping green. Front pins are more accessible.", shape: { type: "par3", bunkers: 3 } },
    { number: 14, par: 4, yards: 467, hcp: 4,  scoring_avg: 4.26, diff_rank: 4,  note: "Demanding long par 4 with a narrow approach corridor.", shape: { type: "straight", bunkers: 2 } },
    { number: 15, par: 4, yards: 449, hcp: 6,  scoring_avg: 4.20, diff_rank: 6,  note: "Dogleg left with OB left. Premium on keeping the ball in the short grass.", shape: { type: "dogleg-left", bunkers: 2 } },
    { number: 16, par: 5, yards: 523, hcp: 10, scoring_avg: 4.68, diff_rank: 10, note: "Birdie hole for bombers, but water right catches aggressive seconds.", shape: { type: "dogleg-right", water: true, bunkers: 1 } },
    { number: 17, par: 3, yards: 137, hcp: 8,  scoring_avg: 3.32, diff_rank: 8,  note: "The most famous par 3 in professional golf. Island green. Wind determines everything.", shape: { type: "par3", water: true, bunkers: 0 } },
    { number: 18, par: 4, yards: 447, hcp: 2,  scoring_avg: 4.28, diff_rank: 2,  note: "Amphitheatre finishing hole. Water left from tee to green. Sunday drama guaranteed.", shape: { type: "straight", water: true, bunkers: 2 } },
  ],
}

/* ─── Pebble Beach ──────────────────────────────────────────────────── */
const PEBBLE_BEACH: CourseData = {
  course_key: "pebble_beach",
  name: "Pebble Beach Golf Links",
  location: "Pebble Beach, CA",
  par: 72, yards: 6972,
  notes: "Host of multiple US Opens and the AT&T Pro-Am. Iconic cliffside holes along Stillwater Cove.",
  holes: [
    { number: 1,  par: 4, yards: 381, hcp: 9,  scoring_avg: 4.14, diff_rank: 9,  note: "Gentle opener. Fairway slopes left toward trees.", shape: { type: "straight", bunkers: 1 } },
    { number: 2,  par: 5, yards: 502, hcp: 13, scoring_avg: 4.68, diff_rank: 13, note: "Dogleg right par 5 with OB right. Birdie chance in calm conditions.", shape: { type: "dogleg-right", bunkers: 2 } },
    { number: 3,  par: 4, yards: 388, hcp: 11, scoring_avg: 4.18, diff_rank: 11, note: "Short par 4 with bunkers protecting the small green.", shape: { type: "straight", bunkers: 2 } },
    { number: 4,  par: 4, yards: 331, hcp: 17, scoring_avg: 4.02, diff_rank: 17, note: "Driveable par 4. Eagle putts are possible for the longest hitters.", shape: { type: "dogleg-left", bunkers: 1 } },
    { number: 5,  par: 3, yards: 188, hcp: 15, scoring_avg: 3.17, diff_rank: 15, note: "Coastal par 3. Wind off the Pacific makes club selection tricky.", shape: { type: "par3", water: true, bunkers: 2 } },
    { number: 6,  par: 5, yards: 516, hcp: 3,  scoring_avg: 4.73, diff_rank: 3,  note: "Clifftop par 5 with ocean left. One of the most scenic holes in golf.", shape: { type: "dogleg-left", water: true, bunkers: 1 } },
    { number: 7,  par: 3, yards: 106, hcp: 18, scoring_avg: 3.05, diff_rank: 18, note: "Postage-stamp green above the cove. Shortest hole, highest drama.", shape: { type: "par3", water: true, bunkers: 3 } },
    { number: 8,  par: 4, yards: 418, hcp: 1,  scoring_avg: 4.38, diff_rank: 1,  note: "Hardest hole. Blind approach over the cliff edge. One of golf's great challenges.", shape: { type: "dogleg-right", water: true, bunkers: 2 } },
    { number: 9,  par: 4, yards: 466, hcp: 5,  scoring_avg: 4.31, diff_rank: 5,  note: "Long par 4 hugging the coastline. Approach exposed to full ocean wind.", shape: { type: "straight", water: true, bunkers: 1 } },
    { number: 10, par: 4, yards: 495, hcp: 7,  scoring_avg: 4.29, diff_rank: 7,  note: "Tight driving hole with trees right and a long approach.", shape: { type: "dogleg-left", bunkers: 2 } },
    { number: 11, par: 4, yards: 380, hcp: 16, scoring_avg: 4.10, diff_rank: 16, note: "Short par 4 with a wide fairway and challenging green complex.", shape: { type: "straight", bunkers: 2 } },
    { number: 12, par: 3, yards: 202, hcp: 12, scoring_avg: 3.21, diff_rank: 12, note: "Long par 3 over a valley. Green slopes toward Stillwater Cove.", shape: { type: "par3", bunkers: 2 } },
    { number: 13, par: 4, yards: 392, hcp: 10, scoring_avg: 4.16, diff_rank: 10, note: "Dogleg right. Second shot plays uphill to a tiered green.", shape: { type: "dogleg-right", bunkers: 2 } },
    { number: 14, par: 5, yards: 572, hcp: 6,  scoring_avg: 4.78, diff_rank: 6,  note: "The longest hole. Tree-lined with fairway bunkers threatening the layup zone.", shape: { type: "straight", bunkers: 3 } },
    { number: 15, par: 4, yards: 397, hcp: 14, scoring_avg: 4.12, diff_rank: 14, note: "Short par 4 to a narrow green — more difficult than the card suggests.", shape: { type: "straight", bunkers: 2 } },
    { number: 16, par: 4, yards: 403, hcp: 4,  scoring_avg: 4.24, diff_rank: 4,  note: "Tight coastal hole with OB left and bunkers right. Demanding iron shot.", shape: { type: "dogleg-left", water: true, bunkers: 2 } },
    { number: 17, par: 3, yards: 178, hcp: 2,  scoring_avg: 3.35, diff_rank: 2,  note: "Iconic Cape hole over the ocean. Tom Watson's chip-in here in 1982 defines the lore.", shape: { type: "par3", water: true, bunkers: 1 } },
    { number: 18, par: 5, yards: 543, hcp: 8,  scoring_avg: 4.80, diff_rank: 8,  note: "Ocean left the entire length. The most beautiful finishing hole in golf.", shape: { type: "straight", water: true, bunkers: 2 } },
  ],
}

/* ─── Muirfield Village (Memorial) ────────────────────────────────── */
const MUIRFIELD_VILLAGE: CourseData = {
  course_key: "muirfield_village",
  name: "Muirfield Village Golf Club",
  location: "Dublin, OH",
  par: 72, yards: 7392,
  notes: "Jack Nicklaus's home course and host of the Memorial Tournament. Demanding bentgrass greens.",
  holes: [
    { number: 1,  par: 4, yards: 455, hcp: 5,  scoring_avg: 4.22, diff_rank: 5,  note: "Long par 4 with a dogleg right. Wide fairway but green is well-protected.", shape: { type: "dogleg-right", bunkers: 2 } },
    { number: 2,  par: 5, yards: 455, hcp: 15, scoring_avg: 4.61, diff_rank: 15, note: "Short par 5 that's reachable in two. Creek guards the approach.", shape: { type: "straight", water: true, bunkers: 1 } },
    { number: 3,  par: 3, yards: 178, hcp: 13, scoring_avg: 3.18, diff_rank: 13, note: "Downhill par 3. Green falls away on all sides.", shape: { type: "par3", bunkers: 3 } },
    { number: 4,  par: 4, yards: 430, hcp: 3,  scoring_avg: 4.28, diff_rank: 3,  note: "Precision driving required between bunkers. Small sloped green.", shape: { type: "straight", bunkers: 3 } },
    { number: 5,  par: 5, yards: 527, hcp: 17, scoring_avg: 4.68, diff_rank: 17, note: "Uphill par 5 with a challenging two-tier green complex.", shape: { type: "dogleg-left", bunkers: 2 } },
    { number: 6,  par: 4, yards: 444, hcp: 7,  scoring_avg: 4.24, diff_rank: 7,  note: "Slight dogleg with a long approach to an elevated green.", shape: { type: "dogleg-right", bunkers: 2 } },
    { number: 7,  par: 4, yards: 563, hcp: 1,  scoring_avg: 4.35, diff_rank: 1,  note: "Hardest hole. Long two-shot demands perfect club selection for a blind second.", shape: { type: "straight", bunkers: 2 } },
    { number: 8,  par: 3, yards: 182, hcp: 11, scoring_avg: 3.20, diff_rank: 11, note: "Long iron to a shallow green pinched by bunkers.", shape: { type: "par3", bunkers: 2 } },
    { number: 9,  par: 4, yards: 411, hcp: 9,  scoring_avg: 4.18, diff_rank: 9,  note: "Short par 4 with a tight driving window. Approach over a pond.", shape: { type: "dogleg-left", water: true, bunkers: 1 } },
    { number: 10, par: 4, yards: 441, hcp: 6,  scoring_avg: 4.23, diff_rank: 6,  note: "Slight dogleg right. Pond protects the right side on the approach.", shape: { type: "dogleg-right", water: true, bunkers: 1 } },
    { number: 11, par: 4, yards: 567, hcp: 2,  scoring_avg: 4.31, diff_rank: 2,  note: "Tree-lined monster. Creek crossing on the approach makes club selection vital.", shape: { type: "straight", water: true, bunkers: 2 } },
    { number: 12, par: 3, yards: 184, hcp: 16, scoring_avg: 3.15, diff_rank: 16, note: "Downhill par 3 to a green surrounded by deep bunkers.", shape: { type: "par3", bunkers: 4 } },
    { number: 13, par: 5, yards: 596, hcp: 14, scoring_avg: 4.75, diff_rank: 14, note: "Longest hole on the course. Risk-reward second shot over water.", shape: { type: "dogleg-left", water: true, bunkers: 2 } },
    { number: 14, par: 4, yards: 363, hcp: 18, scoring_avg: 4.05, diff_rank: 18, note: "Short driveable par 4 but the green falls away severely.", shape: { type: "straight", bunkers: 2 } },
    { number: 15, par: 4, yards: 499, hcp: 4,  scoring_avg: 4.26, diff_rank: 4,  note: "Long and demanding. Uphill approach to a back-to-front sloped green.", shape: { type: "straight", bunkers: 2 } },
    { number: 16, par: 3, yards: 204, hcp: 10, scoring_avg: 3.28, diff_rank: 10, note: "Signature hole. Pond fronts the green. Intimidating tee shot.", shape: { type: "par3", water: true, bunkers: 2 } },
    { number: 17, par: 4, yards: 430, hcp: 8,  scoring_avg: 4.19, diff_rank: 8,  note: "Picturesque par 4 around a pond. Requires confident second over water.", shape: { type: "dogleg-right", water: true, bunkers: 1 } },
    { number: 18, par: 4, yards: 444, hcp: 12, scoring_avg: 4.21, diff_rank: 12, note: "Amphitheatre finish. Long second to a well-protected green — Sunday drama awaits.", shape: { type: "straight", bunkers: 3 } },
  ],
}

/* ─── Bay Hill (Arnold Palmer Invitational) ─────────────────────────── */
const BAY_HILL: CourseData = {
  course_key: "bay_hill",
  name: "Bay Hill Club & Lodge",
  location: "Orlando, FL",
  par: 72, yards: 7454,
  notes: "Arnold Palmer's home course and host of the Invitational. Famous for its demanding 18th.",
  holes: [
    { number: 1,  par: 4, yards: 441, hcp: 7,  scoring_avg: 4.18, diff_rank: 7,  note: "Opening hole demands a long, accurate drive to a tight fairway.", shape: { type: "straight", bunkers: 2 } },
    { number: 2,  par: 5, yards: 218, hcp: 17, scoring_avg: 4.71, diff_rank: 17, note: "Short par 5, but bunkers throughout make it tricky to be aggressive.", shape: { type: "straight", bunkers: 3 } },
    { number: 3,  par: 4, yards: 390, hcp: 13, scoring_avg: 4.15, diff_rank: 13, note: "Short par 4 with a lake right. Driver isn't always the smart play.", shape: { type: "dogleg-right", water: true, bunkers: 1 } },
    { number: 4,  par: 4, yards: 426, hcp: 5,  scoring_avg: 4.23, diff_rank: 5,  note: "Strong two-shot hole. Approach to an elevated green protected by bunkers.", shape: { type: "straight", bunkers: 2 } },
    { number: 5,  par: 4, yards: 393, hcp: 15, scoring_avg: 4.12, diff_rank: 15, note: "Slight dogleg. Front-left pin placement is the most demanding.", shape: { type: "dogleg-left", bunkers: 2 } },
    { number: 6,  par: 3, yards: 223, hcp: 9,  scoring_avg: 3.26, diff_rank: 9,  note: "Long par 3 over water. Tiger's famous iron at the 2008 tournament.", shape: { type: "par3", water: true, bunkers: 2 } },
    { number: 7,  par: 4, yards: 437, hcp: 3,  scoring_avg: 4.28, diff_rank: 3,  note: "Dogleg right. Second shot uphill to a small green with deep bunkers front.", shape: { type: "dogleg-right", bunkers: 3 } },
    { number: 8,  par: 4, yards: 370, hcp: 11, scoring_avg: 4.11, diff_rank: 11, note: "Shorter par 4. Aggressive tee shots can run through the fairway into rough.", shape: { type: "straight", bunkers: 1 } },
    { number: 9,  par: 4, yards: 460, hcp: 1,  scoring_avg: 4.33, diff_rank: 1,  note: "Hardest hole. Long par 4 with a demanding second shot uphill to a sloped green.", shape: { type: "straight", bunkers: 2 } },
    { number: 10, par: 4, yards: 417, hcp: 8,  scoring_avg: 4.16, diff_rank: 8,  note: "Dogleg left with a large tree in play for those who cut the corner.", shape: { type: "dogleg-left", bunkers: 2 } },
    { number: 11, par: 4, yards: 392, hcp: 14, scoring_avg: 4.12, diff_rank: 14, note: "Short par 4 but the green falls away dramatically at the back.", shape: { type: "straight", bunkers: 2 } },
    { number: 12, par: 5, yards: 569, hcp: 12, scoring_avg: 4.68, diff_rank: 12, note: "Reachable par 5 with a lake on the approach. Birdie opportunity for the bold.", shape: { type: "dogleg-right", water: true, bunkers: 1 } },
    { number: 13, par: 3, yards: 207, hcp: 16, scoring_avg: 3.22, diff_rank: 16, note: "Elevated tee shot over a pond. Wind direction can change the club by two.", shape: { type: "par3", water: true, bunkers: 2 } },
    { number: 14, par: 4, yards: 466, hcp: 2,  scoring_avg: 4.29, diff_rank: 2,  note: "Long demanding par 4 to an elevated green. Front bunker is very deep.", shape: { type: "straight", bunkers: 3 } },
    { number: 15, par: 4, yards: 404, hcp: 10, scoring_avg: 4.17, diff_rank: 10, note: "Gentle dogleg left. Front-right pin positions are the most challenging.", shape: { type: "dogleg-left", bunkers: 2 } },
    { number: 16, par: 4, yards: 445, hcp: 4,  scoring_avg: 4.24, diff_rank: 4,  note: "Lake runs the full right side. This hole has claimed many tournaments.", shape: { type: "straight", water: true, bunkers: 1 } },
    { number: 17, par: 3, yards: 219, hcp: 6,  scoring_avg: 3.29, diff_rank: 6,  note: "Long par 3. Back-left pin is the Sunday classic. Water left, deep bunker right.", shape: { type: "par3", water: true, bunkers: 2 } },
    { number: 18, par: 4, yards: 441, hcp: 18, scoring_avg: 4.31, diff_rank: 18, note: "The famous finishing hole. Lake all the way up the left side. Iconic closing moments.", shape: { type: "dogleg-left", water: true, bunkers: 2 } },
  ],
}

/* ─── Registry ──────────────────────────────────────────────────────── */
export const ALL_COURSES: CourseData[] = [
  AUGUSTA,
  TPC_SAWGRASS,
  PEBBLE_BEACH,
  MUIRFIELD_VILLAGE,
  BAY_HILL,
]

export const COURSE_MAP: Record<string, CourseData> = Object.fromEntries(
  ALL_COURSES.map(c => [c.course_key, c])
)

/** Map a tournament event name to a course key */
export function eventToCourseKey(eventName: string | null | undefined): string | null {
  if (!eventName) return null
  const n = eventName.toLowerCase()
  if (n.includes("masters"))           return "augusta_national"
  if (n.includes("players"))           return "tpc_sawgrass"
  if (n.includes("pebble") || n.includes("at&t"))  return "pebble_beach"
  if (n.includes("memorial"))          return "muirfield_village"
  if (n.includes("arnold palmer") || n.includes("bay hill")) return "bay_hill"
  return null
}

/* Hecate — window logic.
 *
 * Vietnamese is the default because the team reads Vietnamese; every string
 * lives in STRINGS so switching the default is one line, and so no sentence
 * is ever hard-coded into the markup.
 *
 * The screens follow the order a person actually works in: pick a folder,
 * see what is in it, choose, run, judge. The scan step in the middle is the
 * important one — it costs nothing and it stops someone starting a ninety
 * file run by accident.
 */

const STRINGS = {
  vi: {
    tagline: "Từ điển dữ liệu và nguồn gốc dữ liệu",
    step1: "Chọn thư mục", step2: "Chọn nội dung", step3: "Kết quả",

    chooseTitle: "Chọn thư mục tài liệu",
    chooseLede: "Chọn thư mục chứa tài liệu nguồn. Chương trình sẽ tự nhận biết đó là kho Excel hay thư mục SQL.",
    chooseBtn: "Chọn thư mục…",
    chooseHint: "Chưa có gì chạy ở bước này. Chọn thư mục là an toàn.",
    whatIsTitle: "Chương trình này làm gì?",
    whatIsBody: "Nó đọc các tài liệu mô tả dữ liệu và lập ra bảng: mỗi trường dữ liệu đến từ đâu, đi qua những chặng nào, và được biến đổi ra sao. Mỗi giá trị đều kèm tên tệp đã nêu ra giá trị đó, để bạn có thể mở tệp gốc và đối chiếu.",

    scanTitle: "Tìm thấy trong thư mục",
    selectAll: "Chọn tất cả",
    back: "Quay lại",
    runBtn: "Bắt đầu chạy",
    quotaTitle: "Chạy nhiều mục sẽ mất thời gian",
    quotaBody: "Mỗi tệp là một lượt gọi AI. Lần đầu chạy có thể mất vài phút; những lần sau đọc từ bộ nhớ đệm nên nhanh hơn nhiều.",
    modeArchive: "Kho Excel", modeSql: "Thư mục SQL",
    foundArchive: (n, m, s) => `<b>${n}</b> bảng đích có thể lập từ điển, trong tổng số <b>${m}</b> bảng đã lập chỉ mục. Các chặng: <b>${s}</b>.`,
    foundSql: (n) => `<b>${n}</b> tệp view (.sql). Mỗi tệp là một view, và bản thân tệp đó chứa toàn bộ nguồn gốc dữ liệu của view.`,
    selected: (n, t) => `Đã chọn ${n} / ${t}`,

    runTitle: "Đang chạy…",
    runLede: "Mỗi tệp được đọc một lần rồi lưu vào bộ nhớ đệm. Bạn có thể để cửa sổ này chạy nền.",
    stopBtn: "Dừng lại",
    stopping: "Đang dừng…",
    stoppingLede: "Sẽ dừng sau khi đọc xong tệp hiện tại. Tệp đang gửi cho AI vẫn phải chờ trả lời xong.",
    stoppedTitle: "Đã dừng",
    stoppedBody: (n) => `Chưa lập từ điển nên không có tệp kết quả nào được ghi ra. ${n} tệp đã đọc xong vẫn được giữ trong bộ nhớ đệm, nên chạy lại sẽ không phải đọc lại số tệp đó.`,

    checksTitle: "Các kiểm tra tự động",
    checksLede: "Những kiểm tra này chạy máy móc trên mọi lần chạy. Chúng cho biết kết quả có đáng tin đến mức nào.",
    coverageTitle: "Mức độ điền đủ",
    coverageLede: "Ô trống không phải lúc nào cũng là lỗi. Đôi khi tài liệu gốc vốn không ghi. Đây là số liệu, không phải phán xét.",
    problemsTitle: "Tệp gặp sự cố",

    chkFidelity: "Mọi tên bảng và cột đều khớp nguyên văn với tài liệu",
    chkFidelityNote: "Kiểm tra từng ký tự. Tên bị bịa ra sẽ bị bắt ở đây.",
    chkComplete: "Số trường đích khớp với số dòng của tệp",
    chkCompleteNote: "Đếm số trường đích riêng biệt, không đếm bản ghi.",
    chkCompletePartNote: (n) => `Đếm số trường đích riêng biệt. Còn ${n} tệp không kiểm tra được vì chương trình không nhận ra dòng tiêu đề của tệp đó.`,
    chkCompleteNone: "Không kiểm tra được số trường đích",
    chkCompleteNoneNote: "Chương trình không nhận ra dòng tiêu đề của các tệp này nên không biết tệp có bao nhiêu dòng dữ liệu. Đây KHÔNG phải là đã đạt, mà là chưa kiểm tra được. Hãy tự đối chiếu số dòng bằng Excel.",
    layoutUnknown: (found, wants) => `Thư mục này không giống một kho tài liệu mà chương trình nhận ra.\n\nTrong thư mục có: ${found}\nChương trình đang tìm: ${wants}`,
    layoutAsk: "Nếu kho tài liệu này có cấu trúc khác, bạn cần một tệp mô tả cấu trúc (archive.json). Chọn tệp đó bây giờ?",
    layoutStillNo: "Vẫn không đọc được kho tài liệu với tệp mô tả này.",
    noSubfolders: "(không có thư mục con nào)",
    chkSchema: "Mọi bản ghi đúng cấu trúc quy định",
    chkFiles: "Số tệp đã đọc",
    chkFilesNote: (c, t) => `${c} tệp đọc mới, ${t - c} tệp lấy từ bộ nhớ đệm.`,
    chkErrors: "Tệp không đọc được",
    chkErrorsNote: "Lần chạy vẫn tiếp tục; chạy lại sẽ chỉ thử lại những tệp này.",
    chkUnknown: "không rõ",

    statRecords: "bản ghi", statFields: "trường đích riêng biệt",
    statChains: "chuỗi đầy đủ", statFiles: "tệp đã đọc",

    browseTitle: "Xem từng trường",
    browseLede: "Bấm vào một dòng để xem toàn bộ hành trình của trường đó và tệp đã nêu ra từng bước.",
    searchPlaceholder: "Tìm bảng hoặc cột…",
    colTable: "Bảng đích", colColumn: "Cột đích", colType: "Kiểu dữ liệu",
    colDesc: "Mô tả", colChain: "Chuỗi",
    showMore: "Xem thêm",
    rowInfo: (shown, total) => `Hiển thị ${shown} / ${total} bản ghi`,
    noMatch: (q) => `Không có trường nào khớp với "${q}".`,
    noRecords: "Lần chạy này không tạo ra bản ghi nào.",
    chainPill: (s) => `${s} chặng`,
    nToOne: (n) => `n→1, ${n} nguồn`,

    newRun: "Chạy lần mới", openFolder: "Mở thư mục kết quả", openExcel: "Mở tệp Excel",

    drwSources: "nguồn",
    drwOrigin: "Chặng gốc. Không có chặng nào phía trước.",
    drwNoSource: "Tệp mô tả chặng này không ghi nguồn nào cho trường.",
    drwFrom: "Lấy từ", drwLogic: "Phép biến đổi", drwEvidence: "Tệp đã nêu điều này",
    drwType: "Kiểu", drwDesc: "Mô tả",
    roleValue: "giá trị", roleJoin: "join", roleCondition: "điều kiện",
    padded: "có khoảng trắng thừa",
    paddedTip: "Tên trong tài liệu gốc có khoảng trắng ở đầu hoặc cuối. Chương trình giữ nguyên như tài liệu, không tự cắt bỏ.",

    errNoFolder: "Không đọc được thư mục này.",
  },

  en: {
    tagline: "Data dictionary and lineage",
    step1: "Choose folder", step2: "Choose what to build", step3: "Results",

    chooseTitle: "Choose a documentation folder",
    chooseLede: "Pick the folder holding the source documents. The program works out on its own whether it is an Excel archive or a folder of SQL views.",
    chooseBtn: "Choose folder…",
    chooseHint: "Nothing runs at this step. Choosing a folder is safe.",
    whatIsTitle: "What does this program do?",
    whatIsBody: "It reads documents that describe data and builds a table: where every field came from, which stages it passed through, and how it was transformed. Every value carries the name of the file that stated it, so you can open that file and check it yourself.",

    scanTitle: "Found in this folder",
    selectAll: "Select all",
    back: "Back",
    runBtn: "Start run",
    quotaTitle: "Building many items takes time",
    quotaBody: "Each file is one AI call. A first run can take several minutes; later runs read from the cache and are much faster.",
    modeArchive: "Excel archive", modeSql: "SQL folder",
    foundArchive: (n, m, s) => `<b>${n}</b> target tables can be built, out of <b>${m}</b> tables indexed. Stages: <b>${s}</b>.`,
    foundSql: (n) => `<b>${n}</b> view scripts (.sql). Each file is one view, and that file holds the view's entire lineage.`,
    selected: (n, t) => `${n} of ${t} selected`,

    runTitle: "Running…",
    runLede: "Each file is read once and then cached. You can leave this window in the background.",
    stopBtn: "Stop",
    stopping: "Stopping…",
    stoppingLede: "It will stop once the current file finishes. A file already sent to the AI has to wait for its reply.",
    stoppedTitle: "Stopped",
    stoppedBody: (n) => `No dictionary was assembled, so no result files were written. The ${n} file(s) already read are kept in the cache, so running again will not re-read them.`,

    checksTitle: "Automatic checks",
    checksLede: "These run mechanically on every run. They are what tells you how far the output can be trusted.",
    coverageTitle: "How much got filled in",
    coverageLede: "A blank is not always a defect. Sometimes the source document simply does not say. These are counts, not judgements.",
    problemsTitle: "Files with problems",

    chkFidelity: "Every table and column name matches the document verbatim",
    chkFidelityNote: "Checked character by character. An invented name is caught here.",
    chkComplete: "Target field count matches the file's row count",
    chkCompleteNote: "Counts distinct target fields, not records.",
    chkCompletePartNote: (n) => `Counts distinct target fields. ${n} file(s) could not be checked because their header row was not recognised.`,
    chkCompleteNone: "Target field count could not be checked",
    chkCompleteNoneNote: "The header row of these files was not recognised, so the program does not know how many data rows they hold. This is NOT a pass, it is unchecked. Compare the row counts yourself in Excel.",
    layoutUnknown: (found, wants) => `This folder does not look like an archive the program recognises.\n\nSubfolders found: ${found}\nLooking for: ${wants}`,
    layoutAsk: "If this archive has a different shape, it needs a layout file (archive.json). Choose one now?",
    layoutStillNo: "Still could not read the archive with that layout file.",
    noSubfolders: "(no subfolders)",
    chkSchema: "Every record has the required shape",
    chkFiles: "Files read",
    chkFilesNote: (c, t) => `${c} read fresh, ${t - c} from cache.`,
    chkErrors: "Files that could not be read",
    chkErrorsNote: "The run carried on; running again retries only these.",
    chkUnknown: "not stated",

    statRecords: "records", statFields: "distinct target fields",
    statChains: "complete chains", statFiles: "files read",

    browseTitle: "Browse the fields",
    browseLede: "Click a row to see that field's whole journey and the file that stated each step.",
    searchPlaceholder: "Search table or column…",
    colTable: "Target table", colColumn: "Target column", colType: "Datatype",
    colDesc: "Description", colChain: "Chain",
    showMore: "Show more",
    rowInfo: (shown, total) => `Showing ${shown} of ${total} records`,
    noMatch: (q) => `No field matches "${q}".`,
    noRecords: "This run produced no records.",
    chainPill: (s) => `${s} stages`,
    nToOne: (n) => `n→1, ${n} sources`,

    newRun: "New run", openFolder: "Open results folder", openExcel: "Open Excel file",

    drwSources: "sources",
    drwOrigin: "Origin stage. Nothing upstream of it.",
    drwNoSource: "The file describing this stage states no source for the field.",
    drwFrom: "Comes from", drwLogic: "Transformation", drwEvidence: "File that stated this",
    drwType: "Type", drwDesc: "Description",
    roleValue: "value", roleJoin: "join", roleCondition: "condition",
    padded: "padded in source",
    paddedTip: "The name in the source document has leading or trailing spaces. The program keeps it exactly as written rather than trimming it.",

    errNoFolder: "That folder could not be read.",
  },
};

let lang = "vi";
const T = () => STRINGS[lang];

const state = {
  folder: null, mode: null, items: [], selected: new Set(),
  result: null, shown: 0, query: "", total: 0,
  runPhase: null, stoppedFiles: 0,
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ── language ──────────────────────────────────────────────────────────── */

function applyLanguage() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-t]").forEach((el) => {
    const value = T()[el.dataset.t];
    if (typeof value === "string") el.textContent = value;
  });
  $("search").placeholder = T().searchPlaceholder;
  $("langToggle").textContent = lang === "vi" ? "EN" : "VI";
  if (state.mode) renderScanSummary();
  if (state.runPhase) setRunPhase(state.runPhase);
  if (state.result) renderResults();
}

$("langToggle").onclick = () => { lang = lang === "vi" ? "en" : "vi"; applyLanguage(); };

/* ── view switching ────────────────────────────────────────────────────── */

function show(view, step) {
  ["choose", "scan", "run", "results"].forEach((name) => {
    $("view-" + name).hidden = name !== view;
  });
  document.querySelectorAll(".step").forEach((el) => {
    const n = Number(el.dataset.step);
    el.classList.toggle("active", n === step);
    el.classList.toggle("done", n < step);
  });
  document.querySelector("main").scrollTop = 0;
}

/* ── 1. choose ─────────────────────────────────────────────────────────── */

// An archive whose folders are named differently is not a broken archive, it
// is a differently-shaped one, and the program handles that through a layout
// file. So an unrecognised folder offers to load one rather than dead-ending
// on a message naming folders from somebody else's archive.
async function scanFolder(folder, layoutPath) {
  const scan = await window.pywebview.api.scan(folder, layoutPath || null);
  if (scan.ok) return scan;

  if (!scan.needs_layout) { alert(scan.error || T().errNoFolder); return null; }

  const found = (scan.found_dirs || []).join(", ") || T().noSubfolders;
  const wants = (scan.expected_dirs || []).join(", ");
  const ask = scan.error
    ? `${scan.error}\n\n${T().layoutAsk}`
    : `${T().layoutUnknown(found, wants)}\n\n${T().layoutAsk}`;

  if (!confirm(ask)) return null;
  const picked = await window.pywebview.api.choose_layout();
  if (!picked.ok) return null;

  const retry = await window.pywebview.api.scan(folder, picked.path);
  if (!retry.ok) { alert(retry.error || T().layoutStillNo); return null; }
  return retry;
}

$("btnChoose").onclick = async () => {
  const picked = await window.pywebview.api.choose_folder();
  if (!picked.ok) return;

  const scan = await scanFolder(picked.folder);
  if (!scan) return;

  state.layoutPath = scan.layout_path || null;
  state.folder = scan.folder;
  state.mode = scan.mode;
  state.items = scan.items;
  state.scan = scan;
  state.selected = new Set(scan.items);

  renderScanSummary();
  renderPicker();
  show("scan", 2);
};

/* ── 2. what to build ──────────────────────────────────────────────────── */

function renderScanSummary() {
  const scan = state.scan;
  $("scanPath").textContent = scan.folder;
  $("scanMode").textContent = scan.mode === "sql" ? T().modeSql : T().modeArchive;
  $("scanSummary").innerHTML = scan.mode === "sql"
    ? T().foundSql(scan.items.length)
    : T().foundArchive(scan.items.length, scan.indexed, (scan.stages || []).join(" → "));
}

function renderPicker() {
  $("pickList").innerHTML = state.items.map((name, i) => `
    <label class="check">
      <input type="checkbox" data-i="${i}" checked>
      <span>${esc(name)}</span>
    </label>`).join("");

  $("pickList").querySelectorAll("input").forEach((box) => {
    box.onchange = () => {
      const name = state.items[Number(box.dataset.i)];
      box.checked ? state.selected.add(name) : state.selected.delete(name);
      syncPickerHead();
    };
  });
  syncPickerHead();
}

function syncPickerHead() {
  const n = state.selected.size, total = state.items.length;
  $("selCount").textContent = T().selected(n, total);
  $("btnRun").disabled = n === 0;
  $("selectAll").checked = n === total;
  $("selectAll").indeterminate = n > 0 && n < total;
  $("quotaWarn").hidden = n <= 8;
}

$("selectAll").onchange = () => {
  const on = $("selectAll").checked;
  state.selected = on ? new Set(state.items) : new Set();
  $("pickList").querySelectorAll("input").forEach((b) => { b.checked = on; });
  syncPickerHead();
};

$("btnBack").onclick = () => show("choose", 1);

/* ── 3. run ────────────────────────────────────────────────────────────── */

// The run screen says different things at different moments, and the language
// can be switched at any of them. Driving every one of its labels from a
// single phase keeps a mid-run toggle from resetting the heading to
// "Running…" after the run has already stopped.
function setRunPhase(phase, filesConverted) {
  state.runPhase = phase;
  if (filesConverted !== undefined) state.stoppedFiles = filesConverted;

  const running = phase === "running" || phase === "stopping";
  $("runActions").hidden = !running;
  $("btnStop").disabled = phase === "stopping";
  $("btnStop").textContent = phase === "stopping" ? T().stopping : T().stopBtn;
  $("stoppedNote").hidden = phase !== "stopped";
  $("stoppedActions").hidden = running;

  $("runHeading").textContent =
    phase === "stopped" ? T().stoppedTitle : T().runTitle;
  $("runLede").textContent =
    phase === "running" ? T().runLede :
    phase === "stopping" ? T().stoppingLede : "";

  if (phase === "stopped") {
    $("stoppedBody").textContent = T().stoppedBody(state.stoppedFiles || 0);
  }
}

$("btnRun").onclick = async () => {
  $("log").textContent = "";
  $("spinner").classList.remove("done");
  setRunPhase("running");
  show("run", 2);

  // Everything selected means "everything", which is what the CLI does with
  // no --table flag. Sending an empty list keeps the two identical.
  const all = state.selected.size === state.items.length;
  const selected = all ? [] : state.items.filter((n) => state.selected.has(n));

  await window.pywebview.api.start(state.mode, state.folder, selected,
                                   state.layoutPath || null);
};

window.logLine = (line) => {
  const log = $("log");
  log.textContent += line + "\n";
  log.scrollTop = log.scrollHeight;
};

// Stopping cannot take effect mid-file: the only checkpoint is between them,
// because interrupting an API call already in flight would mean paying for a
// reply and discarding it. The button therefore reports that it is stopping,
// rather than claiming the run has already halted.
$("btnStop").onclick = async () => {
  setRunPhase("stopping");
  await window.pywebview.api.stop();
};

$("btnStoppedBack").onclick = () => show("scan", 2);

window.runFinished = (summary) => {
  $("spinner").classList.add("done");

  if (summary.cancelled) {
    setRunPhase("stopped", summary.files_converted || 0);
    return;
  }

  if (!summary.ok) {
    window.logLine("\n⚠︎ " + (summary.error || ""));
    setRunPhase("failed");
    return;
  }
  state.result = summary;
  state.shown = 0;
  state.query = "";
  $("search").value = "";
  renderResults();
  loadRows(true);
  show("results", 3);
};

/* ── 4. results ────────────────────────────────────────────────────────── */

// Coverage values arrive as the strings the CLI prints — "55/83 (66%)".
// Parsed rather than recomputed, so the window can never disagree with
// report.json about a number.
function parseFraction(text) {
  const m = String(text || "").match(/^(\d+)\/(\d+)/);
  if (!m) return null;
  const n = +m[1], d = +m[2];
  return { n, d, pct: d ? Math.round((n / d) * 100) : 0 };
}

function statCard(value, label, tone = "") {
  return `<div class="stat ${tone}"><div class="n">${value}</div>
          <div class="k">${label}</div></div>`;
}

function renderResults() {
  const report = state.result.report || {};
  const coverage = report.coverage || {};
  const sources = report.sources || [];

  /* headline numbers */
  const chains = parseFraction(coverage.complete_chains);
  $("stats").innerHTML = [
    statCard(coverage.records ?? 0, T().statRecords),
    statCard(coverage.distinct_target_fields ?? "—", T().statFields),
    statCard(chains ? chains.pct + "%" : "—", T().statChains,
             chains && chains.pct >= 80 ? "good" : chains && chains.pct < 50 ? "warn" : ""),
    statCard(report.files_read ?? 0, T().statFiles),
  ].join("");

  /* checks — totalled across every file the run read */
  let fidOk = 0, fidTotal = 0, schemaOk = 0, schemaTotal = 0;
  let completeOk = 0, completeKnown = 0, completeUnknown = 0;

  sources.forEach((source) => {
    const metrics = source.metrics || {};
    const fid = parseFraction(metrics.fidelity_verified);
    if (fid) { fidOk += fid.n; fidTotal += fid.d; }
    const schema = parseFraction(metrics.schema_clean_records);
    if (schema) { schemaOk += schema.n; schemaTotal += schema.d; }
    const covered = String(metrics.fields_covered || "");
    if (covered.includes("unknown")) completeUnknown++;
    else {
      const c = parseFraction(covered);
      if (c) { completeKnown++; if (c.n >= c.d) completeOk++; }
    }
  });

  const errors = report.source_errors || [];
  const rows = [];

  rows.push(checkRow(fidTotal > 0 && fidOk === fidTotal,
    T().chkFidelity, `${fidOk}/${fidTotal}`, T().chkFidelityNote));

  // "Not checked" is not "passed", and on an unfamiliar archive it can be
  // most of the files: the row count is found by recognising the sheet's
  // header row, and a caption this program has not seen leaves nothing to
  // compare against. Saying so plainly matters more here than a tidy tick,
  // because this check is what catches a truncated reply.
  if (completeKnown === 0 && completeUnknown > 0) {
    rows.push(checkRow(false, T().chkCompleteNone,
                       `0/${completeUnknown}`, T().chkCompleteNoneNote));
  } else {
    rows.push(checkRow(completeKnown > 0 && completeOk === completeKnown,
      T().chkComplete,
      `${completeOk}/${completeKnown}` +
        (completeUnknown ? ` (+${completeUnknown} ${T().chkUnknown})` : ""),
      completeUnknown ? T().chkCompletePartNote(completeUnknown) : T().chkCompleteNote));
  }

  rows.push(checkRow(schemaTotal > 0 && schemaOk === schemaTotal,
    T().chkSchema, `${schemaOk}/${schemaTotal}`, ""));

  rows.push(checkRow(true, T().chkFiles, String(report.files_read ?? 0),
    T().chkFilesNote(report.files_converted ?? 0, report.files_read ?? 0)));

  if (errors.length) {
    rows.push(checkRow(false, T().chkErrors, String(errors.length), T().chkErrorsNote));
  }
  $("checks").innerHTML = rows.join("");

  $("errorCard").hidden = errors.length === 0;
  $("errlist").innerHTML = errors.map((e) => `<li>${esc(e)}</li>`).join("");

  /* coverage bars — every fractional entry the report carries */
  $("coverage").innerHTML = Object.entries(coverage)
    .filter(([, v]) => parseFraction(v))
    .map(([key, value]) => {
      const f = parseFraction(value);
      const tone = f.pct >= 80 ? "good" : f.pct < 50 ? "warn" : "";
      return `<div class="metric">
        <div class="metric-top"><span>${esc(prettyKey(key))}</span>
        <span class="v">${esc(value)}</span></div>
        <div class="bar ${tone}"><span style="width:${f.pct}%"></span></div>
      </div>`;
    }).join("");
}

function checkRow(ok, label, value, note) {
  return `<div class="checkrow ${ok ? "ok" : "warn"}">
    <span class="tick">${ok ? "✓" : "!"}</span>
    <span class="lbl">${esc(label)}${note ? `<span class="note">${esc(note)}</span>` : ""}</span>
    <span class="val">${esc(value)}</span>
  </div>`;
}

// report.json keys are snake_case identifiers; nothing is translated here
// because these are the report's own field names and a reviewer may need to
// match them against the file.
function prettyKey(key) {
  return key.replace(/_/g, " ").replace(/^(stage|datatype) /, "$1: ");
}

/* ── the field table ───────────────────────────────────────────────────── */

const PAGE = 200;

async function loadRows(reset) {
  if (reset) { state.shown = 0; $("rows").innerHTML = ""; }
  const page = await window.pywebview.api.fields(state.query, state.shown, PAGE);
  state.total = page.total;
  state.shown += page.rows.length;

  $("rows").insertAdjacentHTML("beforeend", page.rows.map((r) => `
    <tr data-i="${r.i}">
      <td class="mono">${esc(r.table)}</td>
      <td class="mono">${esc(r.column)}</td>
      <td class="mono">${esc(r.datatype)}</td>
      <td class="desc ${r.description ? "" : "empty"}">${esc(r.description)}</td>
      <td><span class="pill">${T().chainPill(r.stages)}</span>${
        r.siblings > 1 ? `<span class="pill multi">${T().nToOne(r.siblings)}</span>` : ""}</td>
    </tr>`).join(""));

  $("rows").querySelectorAll("tr[data-i]").forEach((tr) => {
    tr.onclick = () => openDrawer(Number(tr.dataset.i));
  });

  // A search that matches nothing is a state, not a blank panel.
  const nothing = state.total === 0;
  $("tableEmpty").hidden = !nothing;
  $("tableEmpty").textContent = state.query ? T().noMatch(state.query) : T().noRecords;
  $("rowInfo").textContent = nothing ? "" : T().rowInfo(state.shown, state.total);
  $("btnMore").hidden = state.shown >= state.total;
}

$("btnMore").onclick = () => loadRows(false);

let searchTimer;
$("search").oninput = (e) => {
  clearTimeout(searchTimer);
  state.query = e.target.value;
  searchTimer = setTimeout(() => loadRows(true), 180);
};

/* ── the detail drawer ─────────────────────────────────────────────────── */

async function openDrawer(index) {
  const answer = await window.pywebview.api.field_detail(index);
  if (!answer.ok) return;

  const record = answer.record;
  const chain = record.lineage || [];
  const last = chain[chain.length - 1] || {};

  $("drawerTitle").textContent =
    `${(last.table || "").trim()}.${(last.column || "").trim()}`;
  $("drawerSub").textContent = record.description || "";

  $("drawerBody").innerHTML = chain.map((entry) => {
    const sources = entry.sources || [];
    const type = [entry.datatype, entry.size].filter(Boolean).join("(") +
                 (entry.size ? ")" : "");

    // An empty sources list means two different things depending on where in
    // the chain it sits: at the head it is the origin, with nothing upstream
    // to record; anywhere later it means that file simply stated no source
    // for this stage. Saying "first stage" on a cloud entry would be a
    // straightforwardly false claim about the data.
    const isHead = entry === chain[0];

    const sourceBlocks = sources.length
      ? sources.map((s) => `
          <div class="src">
            <span class="src-name">${esc(s.table || "—")}${s.column ? "." + esc(s.column) : ""}</span>
            ${s.role ? `<span class="role">${esc(roleLabel(s.role))}</span>` : ""}
            ${s.transformation_logic
              ? `<div class="src-logic">${esc(s.transformation_logic)}</div>` : ""}
          </div>`).join("")
      : `<div class="empty-note">${esc(isHead ? T().drwOrigin : T().drwNoSource)}</div>`;

    return `<div class="hop">
      <div class="hop-top">
        <span class="hop-stage">${esc(entry.stage || "")}</span>
        <span class="hop-name">${esc((entry.table || "").trim())}.${esc((entry.column || "").trim())}</span>
        ${padMark(entry.table) || padMark(entry.column)}
        ${type ? `<span class="hop-type">${esc(type)}</span>` : ""}
      </div>
      ${sourceBlocks}
      ${entry.offline_path ? `
        <div class="evidence"><b>${esc(T().drwEvidence)}:</b>
          <a data-path="${esc(entry.offline_path)}">${esc(fileName(entry.offline_path))}</a>
        </div>` : ""}
    </div>`;
  }).join("");

  // Clicking the evidence reveals the actual document in Finder. This is the
  // whole point of offline_path: a value on screen can be traced to the file
  // that said it, without anyone reading JSON.
  $("drawerBody").querySelectorAll("a[data-path]").forEach((a) => {
    a.onclick = () => window.pywebview.api.reveal(a.dataset.path);
  });

  $("drawer").hidden = false;
  $("scrim").hidden = false;
}

function roleLabel(role) {
  return { value: T().roleValue, join: T().roleJoin, condition: T().roleCondition }[role] || role;
}

// Emitted values keep the source's own spelling and padding — the dictionary
// reports what the sheet says rather than tidying the bank's data. HTML then
// collapses that whitespace, so a name stored as "RRN              " looks
// identical on screen to a clean one. This marks the difference without
// touching the value: a tester should be able to see that the sheet is
// padded, because that is a true fact about the source.
function padMark(value) {
  const text = String(value ?? "");
  if (!text || text === text.trim()) return "";
  return `<span class="padmark" title="${esc(T().paddedTip)}">${esc(T().padded)}</span>`;
}

function fileName(path) {
  return String(path).split("/").pop();
}

function closeDrawer() { $("drawer").hidden = true; $("scrim").hidden = true; }
$("drawerClose").onclick = closeDrawer;
$("scrim").onclick = closeDrawer;
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

/* ── results actions ───────────────────────────────────────────────────── */

$("btnExcel").onclick = () =>
  window.pywebview.api.open_file(state.result.out_dir + "/output.xlsx");
$("btnFolder").onclick = () =>
  window.pywebview.api.reveal(state.result.out_dir);
$("btnNewRun").onclick = () => show("choose", 1);

/* ── start ─────────────────────────────────────────────────────────────── */

applyLanguage();
show("choose", 1);

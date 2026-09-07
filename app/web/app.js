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
    chooseLede: "Chọn thư mục chứa tài liệu nguồn. Chương trình sẽ tự nhận biết đó là kho Excel, thư mục SQL hay thư mục tài liệu (PDF, Word, PowerPoint).",
    chooseBtn: "Chọn thư mục…",
    chooseHint: "Chưa có gì chạy ở bước này. Chọn thư mục là an toàn.",
    openResultsBtn: "Hoặc mở lại kết quả đã lưu từ lần chạy trước…",
    settingsBtn: "Cài đặt khoá API…",
    setTitle: "Cài đặt mô hình AI",
    setLede: "Ứng dụng gửi từng file tới một mô hình AI để đọc. Mặc định là Gemini với khoá có sẵn — không cần đổi gì. Nếu khoá hỏng, hết quota, hoặc nhóm bạn dùng nhà cung cấp khác, đổi ở đây.",
    setProvider: "Nhà cung cấp",
    setModel: "Mô hình (để trống = mặc định)",
    setKey: "Khoá API",
    setBack: "Quay lại",
    setSave: "Lưu",
    setCurrent: (label, model, src, tail) =>
      `Đang dùng: ${label} — ${model}` +
      (src === "own" ? ` (khoá của bạn …${tail})`
        : src === "bundled" ? ` (khoá có sẵn …${tail})`
        : " (chưa có khoá)"),
    setModelHint: (d) => d ? `Mặc định: ${d}` : "",
    setKeyHint: (url) => `Để trống rồi Lưu để xoá khoá riêng. Lấy khoá tại ${url}`,
    setKeyNone: "Nhà cung cấp này chạy trên máy, không cần khoá.",
    needKey: "Chưa đặt khoá API, nên mọi tệp đều sẽ không đọc được.\n\nMở phần Cài đặt để dán khoá vào trước?",
    setUnavailable: " — chưa cài trong bản này",
    setSaved: (label, model, src, tail) =>
      `Đã lưu: ${label} — ${model}` +
      (src === "own" ? ` (khoá của bạn …${tail})`
        : src === "bundled" ? ` (khoá có sẵn …${tail})`
        : " — CHƯA CÓ KHOÁ, chạy sẽ báo lỗi"),
    colAuthored: "Mô tả (bổ sung)",
    descTitle: "Mô tả trường dữ liệu",
    descFromDocs: "Đọc mô tả từ tài liệu…",
    descDocsReading: "Đang đọc tài liệu… (tốn lượt gọi AI)",
    descDocsDone: (m, u, n) =>
      `Đã đọc ${n} tài liệu: khớp ${m} trường. ${u} mô tả nói về trường không có trong lần chạy này (được ghi nhận, không phải lỗi). Bấm "Xuất file mô tả…" để lấy file đã điền sẵn.`,
    descDocsNone: (exts) =>
      `Không có tài liệu nào đọc được trong thư mục đó. Bản này đọc được: ${exts}`,
    descLede: "Xuất ra file Excel một dòng cho mỗi trường, điền cột \"Mô Tả (bổ sung)\", rồi nạp lại. Mô tả bạn viết KHÔNG ghi vào output.json — file đó chỉ chứa những gì tài liệu nói.",
    descExport: "Xuất file mô tả…",
    descLoad: "Nạp file mô tả đã điền…",
    descNoRun: "Chưa có kết quả nào để xuất. Hãy chạy hoặc mở một kết quả trước.",
    descBadFile: "Không đọc được file này.",
    descExported: (n, path) => `Đã xuất ${n} trường → ${path}`,
    descLoaded: (m, n, orphan) =>
      `Đã nạp ${m}/${n} trường` + (orphan ? `, ${orphan} dòng không khớp trường nào (vẫn giữ trong file)` : ""),
    layoutProposeAsk: "Chương trình có thể tự xem thư mục và ĐỀ XUẤT một cấu hình. Bạn sẽ được đọc và duyệt trước khi dùng. Thử không?",
    layoutProposeAccept: "Dùng cấu hình này? Hãy kiểm tra THỨ TỰ các stage — đó là phần chương trình không thể tự kiểm chứng.",
    proposalTitle: "Đề xuất cấu hình thư mục",
    proposalYes: "Dùng cấu hình này",
    proposalNo: "Huỷ",
    openResultsFail: "Thư mục này không có output.json, nên không phải là kết quả của một lần chạy. Hãy chọn thư mục có tên dạng <tên>_2026-01-31_140530.",
    whatIsTitle: "Chương trình này làm gì?",
    whatIsBody: "Nó đọc các tài liệu mô tả dữ liệu và lập ra bảng: mỗi trường dữ liệu đến từ đâu, đi qua những chặng nào, và được biến đổi ra sao. Mỗi giá trị đều kèm tên tệp đã nêu ra giá trị đó, để bạn có thể mở tệp gốc và đối chiếu.",

    scanTitle: "Tìm thấy trong thư mục",
    selectAll: "Chọn tất cả",
    back: "Quay lại",
    runBtn: "Bắt đầu chạy",
    quotaTitle: "Chạy nhiều mục sẽ mất thời gian",
    quotaBody: "Mỗi tệp là một lượt gọi AI. Lần đầu chạy có thể mất vài phút; những lần sau đọc từ bộ nhớ đệm nên nhanh hơn nhiều.",
    modeArchive: "Kho Excel", modeSql: "Thư mục SQL", modeDocs: "Thư mục tài liệu",
    foundArchive: (n, m, s) => `<b>${n}</b> bảng đích có thể lập từ điển, trong tổng số <b>${m}</b> bảng đã lập chỉ mục. Các chặng: <b>${s}</b>.`,
    foundSql: (n) => `<b>${n}</b> tệp view (.sql). Mỗi tệp là một view, và bản thân tệp đó chứa toàn bộ nguồn gốc dữ liệu của view.`,
    foundDocs: (n) => `<b>${n}</b> tài liệu. Mỗi tài liệu được cắt thành từng phần và đọc riêng từng phần; chuỗi nguồn gốc được ghép lại sau bằng Python.`,
    docsNoAnchor: "Tài liệu không nêu số dòng hay danh sách cột, nên phép kiểm tra \"đủ số bản ghi\" không chạy được cho tài liệu. Phép kiểm tra đối chiếu nguyên văn vẫn chạy: một giá trị bịa ra vẫn bị phát hiện, nhưng một giá trị bị bỏ sót thì không.",
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
    noReader: (types, readable, n) => `Thư mục này có ${n} tài liệu định dạng ${types}, nhưng bản cài đặt hiện tại không đọc được các định dạng đó.\n\nBản này đọc được: ${readable}\n\nĐây không phải lỗi cấu hình — bản gọn nhẹ không kèm bộ đọc cho Word/PowerPoint.`,
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
    chooseLede: "Pick the folder holding the source documents. The program works out on its own whether it is an Excel archive, a folder of SQL views, or a folder of documents (PDF, Word, PowerPoint).",
    chooseBtn: "Choose folder…",
    chooseHint: "Nothing runs at this step. Choosing a folder is safe.",
    openResultsBtn: "Or reopen results saved by an earlier run…",
    settingsBtn: "API key settings…",
    setTitle: "AI model settings",
    setLede: "The app sends each file to an AI model to read. The default is Gemini with the key built in — nothing needs changing. Change it here if that key stops working, runs out of quota, or your team uses a different provider.",
    setProvider: "Provider",
    setModel: "Model (blank = the default)",
    setKey: "API key",
    setBack: "Back",
    setSave: "Save",
    setCurrent: (label, model, src, tail) =>
      `Currently: ${label} — ${model}` +
      (src === "own" ? ` (your key …${tail})`
        : src === "bundled" ? ` (built-in key …${tail})`
        : " (no key set)"),
    setModelHint: (d) => d ? `Default: ${d}` : "",
    setKeyHint: (url) => `Leave blank and Save to clear your key. Get one at ${url}`,
    setKeyNone: "This provider runs on your machine and needs no key.",
    needKey: "No API key is set, so every file would fail to be read.\n\nOpen Settings and paste your key first?",
    setUnavailable: " — not installed in this build",
    setSaved: (label, model, src, tail) =>
      `Saved: ${label} — ${model}` +
      (src === "own" ? ` (your key …${tail})`
        : src === "bundled" ? ` (built-in key …${tail})`
        : " — NO KEY SET, runs will fail"),
    colAuthored: "Description (added)",
    descTitle: "Field descriptions",
    descFromDocs: "Read meanings from documents…",
    descDocsReading: "Reading documents… (this spends API calls)",
    descDocsDone: (m, u, n) =>
      `Read ${n} document(s): ${m} field(s) matched. ${u} meaning(s) describe a field this run did not build (reported, not an error). Use "Export description sheet…" to get the pre-filled file.`,
    descDocsNone: (exts) =>
      `No readable documents in that folder. This build reads: ${exts}`,
    descLede: "Export a spreadsheet with one row per field, fill in the \"Mô Tả (bổ sung)\" column, then load it back. What you write is NOT written into output.json — that file holds only what the documents state.",
    descExport: "Export description sheet…",
    descLoad: "Load a filled-in sheet…",
    descNoRun: "No results to export from. Run something, or open a saved run first.",
    descBadFile: "That file could not be read.",
    descExported: (n, path) => `Exported ${n} field(s) → ${path}`,
    descLoaded: (m, n, orphan) =>
      `Loaded ${m}/${n} field(s)` + (orphan ? `, ${orphan} row(s) matched no field (kept in the file)` : ""),
    layoutProposeAsk: "The program can look at the folder and PROPOSE a layout. You will see it and have to accept it before anything runs. Try that?",
    layoutProposeAccept: "Use this layout? Check the stage ORDER — that is the part the program cannot verify for itself.",
    proposalTitle: "Proposed archive layout",
    proposalYes: "Use this layout",
    proposalNo: "Cancel",
    openResultsFail: "That folder has no output.json, so it is not a results folder. Look for one named like <name>_2026-01-31_140530.",
    whatIsTitle: "What does this program do?",
    whatIsBody: "It reads documents that describe data and builds a table: where every field came from, which stages it passed through, and how it was transformed. Every value carries the name of the file that stated it, so you can open that file and check it yourself.",

    scanTitle: "Found in this folder",
    selectAll: "Select all",
    back: "Back",
    runBtn: "Start run",
    quotaTitle: "Building many items takes time",
    quotaBody: "Each file is one AI call. A first run can take several minutes; later runs read from the cache and are much faster.",
    modeArchive: "Excel archive", modeSql: "SQL folder", modeDocs: "Document folder",
    foundArchive: (n, m, s) => `<b>${n}</b> target tables can be built, out of <b>${m}</b> tables indexed. Stages: <b>${s}</b>.`,
    foundSql: (n) => `<b>${n}</b> view scripts (.sql). Each file is one view, and that file holds the view's entire lineage.`,
    foundDocs: (n) => `<b>${n}</b> documents. Each one is split into sections and every section is read on its own; the chain is joined afterwards, in Python.`,
    docsNoAnchor: "A document states no row count and no column list, so the completeness check cannot run on one. Fidelity still does: an invented value is caught, a dropped one is not.",
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
    noReader: (types, readable, n) => `This folder holds ${n} document(s) of type ${types}, and this build cannot open them.\n\nIt can read: ${readable}\n\nThis is not a configuration problem — the small build ships without the Word/PowerPoint reader.`,
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
  ["choose", "scan", "run", "results", "settings"].forEach((name) => {
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

  // Documents this build has no reader for. Its own message, because the
  // layout offer below would send someone hunting for a config file that
  // cannot help — the folder is fine, the build simply lacks the reader.
  if (scan.error === "no_reader") {
    alert(T().noReader((scan.found_types || []).join(", "),
                       (scan.readable || []).join(", "),
                       scan.count || 0));
    return null;
  }

  if (!scan.needs_layout) { alert(scan.error || T().errNoFolder); return null; }

  // Capped. Same failure as the proposal dialog, one size down: a folder with
  // dozens of subfolders builds a confirm() taller than the screen, and a
  // native dialog cannot scroll to reach its own buttons.
  const cap = (list) => {
    const all = list || [];
    return all.length > 12
      ? all.slice(0, 12).join(", ") + ` … (+${all.length - 12})`
      : all.join(", ");
  };
  const found = cap(scan.found_dirs) || T().noSubfolders;
  const wants = cap(scan.expected_dirs);
  const ask = scan.error
    ? `${scan.error}\n\n${T().layoutAsk}`
    : `${T().layoutUnknown(found, wants)}\n\n${T().layoutAsk}`;

  if (!confirm(ask)) return null;

  // Offer to work one out from the folder itself before asking for a file
  // nobody may have. The proposal is shown in full and has to be accepted —
  // a wrong stage ORDER passes every check this program has and produces a
  // confidently wrong pipeline, so it is never applied on its own.
  let layoutPathToUse = null;
  if (confirm(T().layoutProposeAsk)) {
    const proposed = await window.pywebview.api.propose_layout(folder);
    if (proposed.ok && await askLong(T().proposalTitle, proposed.text,
                                     T().layoutProposeAccept)) {
      layoutPathToUse = proposed.path;
    }
  }
  if (!layoutPathToUse) {
    const picked = await window.pywebview.api.choose_layout();
    if (!picked.ok) return null;
    layoutPathToUse = picked.path;
  }

  const retry = await window.pywebview.api.scan(folder, layoutPathToUse);
  if (!retry.ok) { alert(retry.error || T().layoutStillNo); return null; }
  return retry;
}

$("btnExportDesc").onclick = async () => {
  const r = await window.pywebview.api.export_descriptions();
  if (!r.ok) { alert(r.detail || T().descNoRun); return; }
  $("descStatus").textContent = T().descExported(r.fields, r.path);
};

$("btnDocsDesc").onclick = async () => {
  const r = await window.pywebview.api.descriptions_from_documents();
  if (r.ok === false && r.error) { alert(T().descNoRun); return; }
  if (!r.ok) return;                                   // folder picker cancelled
  $("btnDocsDesc").disabled = true;
  $("descStatus").textContent = T().descDocsReading;
};

// Reading documents costs API calls and runs on a thread, so the answer
// arrives here rather than as a return value.
window.docsFinished = (r) => {
  $("btnDocsDesc").disabled = false;
  if (r.error === "no_documents") {
    $("descStatus").textContent = T().descDocsNone((r.readable || []).join(", "));
    return;
  }
  if (!r.ok) { $("descStatus").textContent = r.error || ""; return; }
  $("descStatus").textContent = T().descDocsDone(
    r.definitions_matched ?? 0, r.definitions_unmatched ?? 0, r.documents ?? 0);
};

$("btnLoadDesc").onclick = async () => {
  const r = await window.pywebview.api.load_descriptions();
  if (r.ok === false && r.error) { alert(r.detail || T().descBadFile); return; }
  if (!r.ok) return;                       // dialog cancelled
  $("descStatus").textContent = T().descLoaded(r.matched, r.fields, r.orphaned);
  loadRows(true);                          // the authored column repopulates
};

async function openSettings() {
  const s = await window.pywebview.api.key_status();
  // A provider this build cannot actually reach is shown, but disabled and
  // labelled. Hiding it would leave someone wondering whether the app supports
  // their vendor at all; offering it would let them pick a dead end.
  $("setProviderSel").innerHTML = s.choices.map((c) =>
    `<option value="${c.name}" ${c.name === s.provider ? "selected" : ""}` +
    `${c.available ? "" : " disabled"}>` +
    `${esc(c.label)}${c.available ? "" : T().setUnavailable}</option>`
  ).join("");
  $("setModelIn").value = s.model || "";
  $("setKeyIn").value = "";
  paintSettings(s);
  $("setStatus").textContent = "";
  show("settings");
}

// Which key a provider needs, and where to get one, changes with the choice —
// so the hints follow the dropdown rather than describing whatever was
// selected when the screen opened.
function paintSettings(s) {
  const chosen = $("setProviderSel").value;
  const info = s.choices.find((c) => c.name === chosen) || {};
  $("setCurrent").textContent = T().setCurrent(s.label, s.model, s.source, s.tail);
  $("setModelHint").textContent = T().setModelHint(info.default_model || "");
  $("setKeyHint").textContent = info.needs_key
    ? T().setKeyHint(info.key_url || "")
    : T().setKeyNone;
  $("setKeyIn").disabled = !info.needs_key;
}

$("btnSettings").onclick = async (event) => {
  event.preventDefault();
  await openSettings();
};

$("setProviderSel").onchange = async () => {
  paintSettings(await window.pywebview.api.key_status());
};

$("btnSetBack").onclick = () => show("choose", 1);

$("btnSetSave").onclick = async () => {
  const after = await window.pywebview.api.save_settings(
    $("setProviderSel").value, $("setModelIn").value, $("setKeyIn").value);
  $("setKeyIn").value = "";
  $("setStatus").textContent = T().setSaved(after.label, after.model,
                                            after.source, after.tail);
  paintSettings(after);
};

$("btnOpenResults").onclick = async (event) => {
  event.preventDefault();
  const opened = await window.pywebview.api.open_results();
  // A cancelled dialog returns ok:false with no error; only a real folder
  // that turned out not to hold results is worth interrupting someone over.
  if (!opened.ok && opened.error === "no_results") {
    alert(T().openResultsFail);
  }
  // On success the page is driven by runFinished(), the same handler a
  // finished run goes through, so there is one render path rather than two.
};

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
  $("scanMode").textContent =
    scan.mode === "sql" ? T().modeSql
    : scan.mode === "docs" ? T().modeDocs
    : T().modeArchive;
  $("scanSummary").innerHTML =
    scan.mode === "sql" ? T().foundSql(scan.items.length)
    : scan.mode === "docs"
      // Said here rather than left to the report, because it is the one check
      // a reviewer would otherwise assume ran. Documents have no anchor for it.
      ? T().foundDocs(scan.items.length) + `<br><span class="muted">${T().docsNoAnchor}</span>`
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
  // Check the key BEFORE starting. Without this, a build shipped with no key
  // baked in starts a run in which every file fails to be read, and the person
  // watching has no way to know that one missing setting is the reason. The
  // settings screen already says "no key set"; nothing pointed anyone at it at
  // the only moment it matters.
  const key = await window.pywebview.api.key_status();
  if (!key.has_key) {
    if (confirm(T().needKey)) show("settings");
    return;
  }

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
      <td class="desc ${r.authored ? "" : "empty"}">${esc(r.authored)}</td>
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
// reports what the sheet says rather than tidying the source data. HTML then
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

/* A scrollable replacement for confirm(), for text that can run long.
   The survey's proposal is a screenful — facts, reasoning and a whole JSON
   layout — and a native confirm() does not scroll, so its buttons ended up off
   the bottom of the screen with the app modal behind them and no way out but
   force-quitting. Anything unbounded goes through here instead. */
function askLong(title, text, question) {
  return new Promise((resolve) => {
    $("proposalTitle").textContent = title;
    $("proposalBody").textContent = text;
    $("proposalAsk").textContent = question;
    $("proposalOk").textContent = T().proposalYes;
    $("proposalNo").textContent = T().proposalNo;
    $("proposal").hidden = false;
    $("scrim").hidden = false;
    $("proposalBody").scrollTop = 0;

    const finish = (answer) => {
      $("proposal").hidden = true;
      $("scrim").hidden = true;
      $("scrim").onclick = closeDrawer;        // give the drawer its scrim back
      document.removeEventListener("keydown", onKey);
      resolve(answer);
    };
    const onKey = (e) => {
      if (e.key === "Escape") finish(false);
      if (e.key === "Enter") finish(true);
    };
    $("proposalOk").onclick = () => finish(true);
    $("proposalNo").onclick = () => finish(false);
    $("scrim").onclick = () => finish(false);
    document.addEventListener("keydown", onKey);
    $("proposalOk").focus();
  });
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

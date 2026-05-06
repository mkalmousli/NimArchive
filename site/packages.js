function renderMarkdown(text, container) {
    const theme = CONFIG[state.theme];
    const lines = text.split('\n');
    let inList = false;
    let listEl = null;
    let inCode = false;
    let codeEl = null;
    let inTable = false;
    let tableEl = null;
    let tableHeader = true;

    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trimEnd();

        if (line.trim().startsWith('```')) {
            if (!inCode) {
                inCode = true;
                codeEl = create("pre", container, {
                    padding: "12px",
                    backgroundColor: theme.bg,
                    border: `1px solid ${theme.border}`,
                    borderRadius: "4px",
                    fontFamily: CONFIG.fonts.mono,
                    fontSize: "11px",
                    overflowX: "hidden",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-all",
                    marginBottom: "12px",
                    lineHeight: "1.4"
                });
            } else { inCode = false; }
            continue;
        }
        if (inCode) { create("div", codeEl).textContent = line; continue; }

        if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
            const cells = line.split('|').map(c => c.trim()).filter((c, idx, arr) => idx > 0 && idx < arr.length - 1);
            if (!inTable) {
                inTable = true;
                tableEl = create("table", container, { width: "100%", borderCollapse: "collapse", marginBottom: "12px", fontSize: "11px", tableLayout: "fixed" });
                tableHeader = true;
            }
            if (cells.every(c => c.startsWith('---'))) { tableHeader = false; continue; }
            const tr = create("tr", tableEl, { borderTop: `1px solid ${theme.border}`, backgroundColor: (tableEl.rows.length % 2 === 0) ? "transparent" : theme.surface });
            cells.forEach(cell => {
                const tag = tableHeader ? "th" : "td";
                const cellEl = create(tag, tr, { padding: "4px 8px", border: `1px solid ${theme.border}`, fontWeight: tableHeader ? "600" : "400", textAlign: "left", wordBreak: "break-all" });
                parseInline(cell, cellEl);
            });
            continue;
        } else { inTable = false; }

        if (line.trim().startsWith('>')) {
            const bq = create("blockquote", container, { margin: "0 0 12px 0", padding: "0 1em", color: theme.dim, borderLeft: `0.2em solid ${theme.border}` });
            parseInline(line.trim().substring(1).trim(), bq); continue;
        }

        if (line.trim().startsWith('#')) {
            let trimmed = line.trim(); let level = 0;
            while (trimmed[level] === '#') level++;
            if (level > 0 && level <= 6) {
                const h = create(`h${level}`, container, { marginTop: "16px", marginBottom: "8px", fontWeight: "600", lineHeight: "1.2", fontSize: level === 1 ? "1.6em" : level === 2 ? "1.3em" : "1.1em", borderBottom: (level <= 2) ? `1px solid ${theme.border}` : "none", paddingBottom: (level <= 2) ? "0.2em" : "0" });
                parseInline(trimmed.substring(level).trim(), h); continue;
            }
        }

        const listMatch = line.match(/^(\s*)([*+-]|\d+\.)\s+(.*)/);
        if (listMatch) {
            const content = listMatch[3];
            if (!inList) {
                inList = true;
                const tag = /^\d+\./.test(listMatch[2]) ? "ol" : "ul";
                listEl = create(tag, container, { paddingLeft: "1.5em", marginBottom: "12px" });
            }
            const li = create("li", listEl, { marginBottom: "0.2em" });
            if (content.startsWith('[ ] ') || content.startsWith('[x] ')) {
                const cb = create("input", li, { marginRight: "6px" }); cb.type = "checkbox"; cb.disabled = true; cb.checked = content.startsWith('[x] ');
                parseInline(content.substring(4), li);
            } else { parseInline(content, li); }
            continue;
        } else { inList = false; }

        if (line.trim().match(/^(?:-{3,}|\*{3,}|_{3,})$/)) {
            create("hr", container, { height: "1px", margin: "16px 0", backgroundColor: theme.border, border: "0" }); continue;
        }

        if (line.trim() === '') continue;
        const p = create("p", container, { marginBottom: "8px" });
        parseInline(line, p);
    }
}

function isMarkdownFile(fileName) {
    return /\.md(?:own|txt)?$/i.test(fileName || "");
}

function parseInline(text, container) {
    const theme = CONFIG[state.theme];
    const tokens = text.split(/(\[.*?\]\(.*?\))|(\*\*.*?\*\*)|(`.*?`)|(<br\s*\/?>)|(<b>.*?<\/b>)|(<i>.*?<\/i>)|(<strong>.*?<\/strong>)|(<em>.*?<\/em>)|(<a\s+.*?href=".*?".*?>.*?<\/a>)|(<sub>.*?<\/sub>)|(<sup>.*?<\/sup>)/i);
    tokens.forEach(token => {
        if (!token) return;
        if (token.startsWith('[') && token.includes('](')) {
            const match = token.match(/\[(.*?)\]\((.*?)\)/);
            if (match) {
                const a = create("a", container, { color: CONFIG.primary, textDecoration: "none" });
                a.href = match[2]; a.target = "_blank"; a.textContent = match[1];
                addHover(a, { textDecoration: "none" }, { textDecoration: "underline" });
                return;
            }
        }
        if (token.startsWith('**') && token.endsWith('**')) {
            create("strong", container, { fontWeight: "600" }).textContent = token.substring(2, token.length - 2); return;
        }
        if (token.startsWith('`') && token.endsWith('`')) {
            const c = create("code", container, { fontFamily: CONFIG.fonts.mono, backgroundColor: theme.surface, padding: "0.1em 0.3em", borderRadius: "4px", fontSize: "90%" });
            c.textContent = token.substring(1, token.length - 1); return;
        }
        const low = token.toLowerCase();
        if (low.startsWith('<br')) { create("br", container); return; }
        if (low.startsWith('<b>') || low.startsWith('<strong>')) { create("strong", container, { fontWeight: "600" }).textContent = token.replace(/<[^>]+>/g, ''); return; }
        if (low.startsWith('<i>') || low.startsWith('<em>')) { create("em", container, { fontStyle: "italic" }).textContent = token.replace(/<[^>]+>/g, ''); return; }
        if (low.startsWith('<sub')) { create("sub", container, { fontSize: "75%", verticalAlign: "sub" }).textContent = token.replace(/<[^>]+>/g, ''); return; }
        if (low.startsWith('<sup')) { create("sup", container, { fontSize: "75%", verticalAlign: "super" }).textContent = token.replace(/<[^>]+>/g, ''); return; }
        if (low.startsWith('<a ')) {
            const h = token.match(/href="([^"]+)"/i); const c = token.match(/>(.*?)<\/a>/i);
            if (h && c) {
                const a = create("a", container, { color: CONFIG.primary, textDecoration: "none" });
                a.href = h[1]; a.target = "_blank"; a.textContent = c[1];
                addHover(a, { textDecoration: "none" }, { textDecoration: "underline" });
                return;
            }
        }
        container.appendChild(document.createTextNode(token));
    });
}

let listContainer;

function renderPackageList() {
    if (!sidebar) return;
    if (!listContainer) { listContainer = create("div", sidebar, { overflowY: "auto", flex: "1" }); }
    while (listContainer.firstChild) listContainer.removeChild(listContainer.firstChild);
    const theme = CONFIG[state.theme];
    for (let name in state.packages) {
        if (state.searchQuery && !name.toLowerCase().includes(state.searchQuery)) continue;
        const pkg = state.packages[name];
        const item = create("div", listContainer, { padding: "6px 12px", cursor: "pointer", fontSize: "12px", display: "flex", flexDirection: "column", gap: "2px" });
        create("div", item, { fontWeight: "500", color: theme.fg }).textContent = name;
        create("div", item, { fontSize: "10px", color: theme.dim }).textContent = pkg.id;
        const isAct = state.selectedPackage === name;
        s(item, { backgroundColor: isAct ? theme.active : "transparent" });
        item.addEventListener("click", () => { state.selectedPackage = name; renderPackageDetail(name); renderPackageList(); });
        addHover(item, { backgroundColor: isAct ? theme.active : "transparent" }, { backgroundColor: theme.surface });
    }
}

async function renderPackageDetail(name) {
    if (!contentArea) return;
    await withLoadingToast(`Loading ${name}...`, async () => {
        while (contentArea.firstChild) contentArea.removeChild(contentArea.firstChild);
        const theme = CONFIG[state.theme];
        const pkg = state.packages[name];
        
        let historyData = null;
        let versionTags = [];
        let latestMeta = null;
        let latestPath = "";
        let latestCode = "";

        try {
            const latestData = await fetchArchiveJson(`packages/${pkg.id}/code/latest.json`);
            latestCode = latestData.code;
            latestPath = `${CONFIG.archiveBaseUrl}/packages/${pkg.id}/code/${latestCode}`;
            latestMeta = await fetchArchiveJson(`packages/${pkg.id}/code/${latestCode}/metadata.json`);
        } catch(e) {}
        try {
            historyData = await fetchArchiveJson(`packages/${pkg.id}/code/all.json`);
        } catch(e) {}
        try {
            const versionsData = await fetchArchiveJson(`packages/${pkg.id}/versions/all.json`);
            versionTags = Array.isArray(versionsData.versions) ? versionsData.versions : [];
        } catch(e) {}

        const detailHeader = create("div", contentArea, { padding: "12px 16px 0 16px", backgroundColor: theme.bg, position: "sticky", top: "0", zIndex: "10" });
        create("div", detailHeader, { fontSize: "16px", fontWeight: "600", marginBottom: "2px" }).textContent = name;
        const info = create("div", detailHeader, { marginTop: "8px", display: "flex", gap: "6px", flexWrap: "wrap" });
        const createChip = (l, v, parent = info) => {
            const chip = create("div", parent, { display: "flex", alignItems: "center", padding: "1px 6px", backgroundColor: theme.surface, border: `1px solid ${theme.border}`, borderRadius: "10px", fontSize: "9px", fontWeight: "500", color: theme.fg });
            create("span", chip, { color: theme.dim, marginRight: "3px", textTransform: "uppercase", fontSize: "8px" }).textContent = l;
            create("span", chip).textContent = v; return chip;
        };
        createChip("TYPE", pkg.type.toUpperCase());
        if (pkg.license) createChip("LICENSE", pkg.license);
        createChip("ADDED", new Date(pkg.added_at * 1000).toLocaleDateString());
        createChip("VERSIONS", String(versionTags.length));

        const headerMetaRow = create("div", detailHeader, { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "16px", marginTop: "12px", flexWrap: "wrap" });
        const urlLink = create("a", headerMetaRow, { color: CONFIG.primary, textDecoration: "none", fontSize: "10px", display: "block", minWidth: "0", flex: "1 1 260px" });
        urlLink.href = pkg.url; urlLink.target = "_blank"; urlLink.textContent = pkg.url;

        const selectorContainer = create("div", headerMetaRow, { display: "flex", gap: "8px", flexWrap: "wrap", justifyContent: "flex-end", marginLeft: "auto" });
        const tabContainer = create("div", detailHeader, { display: "flex", marginTop: "12px", borderBottom: `1px solid ${theme.border}`, gap: "16px" });
        const bodyContainer = create("div", contentArea, { padding: "16px" });
        
        const createSelect = (labelText) => {
            const wrap = create("label", selectorContainer, { display: "flex", flexDirection: "column", gap: "4px", fontSize: "10px", color: theme.dim });
            wrap.textContent = labelText;
            return create("select", wrap, {
                minWidth: "140px",
                padding: "6px 8px",
                border: `1px solid ${theme.border}`,
                borderRadius: "4px",
                backgroundColor: theme.surface,
                color: theme.fg,
                fontSize: "11px"
            });
        };

        const versionSelect = createSelect("VERSION");
        const versionIdSelect = createSelect("ARCHIVE");
        const versionIdCache = new Map();
        const documentCache = new Map();
        const versionLabelCache = new Map();

        const latestOption = create("option", versionSelect);
        latestOption.value = "latest";
        latestOption.textContent = "latest";
        for (const tag of [...versionTags].reverse()) {
            const opt = create("option", versionSelect);
            opt.value = tag;
            opt.textContent = tag;
        }

        let activeTab = latestMeta?.readme ? "readme" : (latestMeta?.license ? "license" : "history");
        let selectedVersion = "latest";
        let selectedVersionId = "latest";
        let selectedMeta = latestMeta;
        let selectedPath = latestPath;

        const getAvailableTabs = () => {
        const tabs = [];
        if (selectedMeta?.readme) tabs.push("readme");
        if (selectedMeta?.license) tabs.push("license");
        if (historyData?.codes?.length) tabs.push("history");
        return tabs;
        };

        const ensureActiveTab = () => {
        const availableTabs = getAvailableTabs();
        if (!availableTabs.includes(activeTab)) {
            activeTab = availableTabs[0] || "history";
        }
        return availableTabs;
        };

        const setVersionIdOptions = (entries, preferred = entries[entries.length - 1]?.id) => {
        while (versionIdSelect.firstChild) versionIdSelect.removeChild(versionIdSelect.firstChild);
        entries.forEach(entry => {
            const opt = create("option", versionIdSelect);
            opt.value = entry.id;
            opt.textContent = entry.label;
        });
        selectedVersionId = preferred;
        versionIdSelect.value = preferred;
        };

        const getVersionEntries = async (tag) => {
        if (versionIdCache.has(tag)) return versionIdCache.get(tag);
        try {
            const data = await fetchArchiveJson(`packages/${pkg.id}/versions/${tag}/all.json`);
            const ids = Array.isArray(data.versions) ? data.versions : [];
            const entries = [];

            for (const id of ids) {
                const cacheKey = `${tag}:${id}`;
                let label = versionLabelCache.get(cacheKey);

                if (!label) {
                    try {
                        const meta = await fetchArchiveJson(`packages/${pkg.id}/versions/${tag}/${id}/metadata.json`);
                        label = new Date(meta.archived_at * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
                    } catch(e) {
                        label = id;
                    }
                    versionLabelCache.set(cacheKey, label);
                }

                entries.push({ id, label });
            }

            versionIdCache.set(tag, entries);
            return entries;
        } catch(e) {
            versionIdCache.set(tag, []);
            return [];
        }
        };

        const loadSelectedDocument = async () => {
        const cacheKey = `${selectedVersion}:${selectedVersionId}`;
        if (documentCache.has(cacheKey)) {
            const cached = documentCache.get(cacheKey);
            selectedMeta = cached.meta;
            selectedPath = cached.path;
            return;
        }

        if (selectedVersion === "latest") {
            selectedMeta = latestMeta;
            selectedPath = latestPath;
        } else {
            const path = `${CONFIG.archiveBaseUrl}/packages/${pkg.id}/versions/${selectedVersion}/${selectedVersionId}`;
            let meta = null;
            try {
                meta = await fetchArchiveJson(`packages/${pkg.id}/versions/${selectedVersion}/${selectedVersionId}/metadata.json`);
            } catch(e) {}
            selectedMeta = meta;
            selectedPath = path;
        }
        documentCache.set(cacheKey, { meta: selectedMeta, path: selectedPath });
        };

        const renderTabs = () => {
        while (tabContainer.firstChild) tabContainer.removeChild(tabContainer.firstChild);
        const availableTabs = ensureActiveTab();
        const allT = [{id:"readme",l:"README"},{id:"license",l:"LICENSE"},{id:"history",l:"HISTORY"}];
        allT.filter(t => availableTabs.includes(t.id)).forEach(t => {
            const isAct = activeTab === t.id;
            const tab = create("div", tabContainer, { padding: "8px 0", fontSize: "11px", fontWeight: isAct ? "600" : "400", color: isAct ? CONFIG.primary : theme.dim, cursor: "pointer", borderBottom: isAct ? `2px solid ${CONFIG.primary}` : "2px solid transparent", marginBottom: "-1px" });
            tab.textContent = t.l;
            tab.addEventListener("click", () => { activeTab = t.id; renderTabs(); renderTabContent(); });
        });
        };

        const renderTabContent = async () => {
        while (bodyContainer.firstChild) bodyContainer.removeChild(bodyContainer.firstChild);
        
        if ((activeTab === "readme" && selectedMeta?.readme) || (activeTab === "license" && selectedMeta?.license)) {
            const isReadme = activeTab === "readme";
            const fileName = isReadme ? selectedMeta.readme : selectedMeta.license;
            const renderAsMarkdown = isMarkdownFile(fileName);
            const wrapper = create("div", bodyContainer, { position: "relative" });
            const sourceBtn = create("button", wrapper, { position: "absolute", top: "10px", right: "10px", padding: "4px 8px", fontSize: "9px", border: `1px solid ${theme.border}`, background: theme.bg, color: theme.dim, borderRadius: "3px", cursor: "pointer", zIndex: "5" });
            sourceBtn.textContent = renderAsMarkdown ? "VIEW SOURCE" : "VIEW RAW";
            
            const contentBox = create("div", wrapper, { padding: "0 8px", fontSize: isReadme ? "12px" : "11px", lineHeight: "1.5" });
            const rawBox = create("pre", wrapper, { display: "none", padding: "0 8px", fontSize: "11px", fontFamily: CONFIG.fonts.mono, whiteSpace: "pre-wrap", margin: "0" });
            
            const relativePath = selectedPath.replace(`${CONFIG.archiveBaseUrl}/`, "");
            const txt = await fetchArchiveText(`${relativePath}/${fileName}`);
            if (renderAsMarkdown) {
                renderMarkdown(txt, contentBox);
            } else {
                contentBox.textContent = txt;
                sourceBtn.style.display = "none";
            }
            rawBox.textContent = txt;

            let showingSource = false;
            sourceBtn.addEventListener("click", () => {
                showingSource = !showingSource;
                sourceBtn.textContent = showingSource ? "VIEW RENDERED" : "VIEW SOURCE";
                contentBox.style.display = showingSource ? "none" : "block";
                rawBox.style.display = showingSource ? "block" : "none";
            });
        } 
        else if (activeTab === "history" && historyData) {
            const list = create("div", bodyContainer);
            for (let id of [...historyData.codes].reverse()) await renderHistoryItem(list, `${CONFIG.archiveBaseUrl}/packages/${pkg.id}/code/${id}`);
        }
        };

        const refreshSelectedDocument = async (message = `Loading ${name}...`) => {
            await withLoadingToast(message, async () => {
                await loadSelectedDocument();
                renderTabs();
                await renderTabContent();
            });
        };

        versionSelect.addEventListener("change", async () => {
            selectedVersion = versionSelect.value;
            if (selectedVersion === "latest") {
                versionIdSelect.disabled = true;
                setVersionIdOptions([{ id: "latest", label: "Latest" }], "latest");
            } else {
                const entries = await getVersionEntries(selectedVersion);
                versionIdSelect.disabled = entries.length === 0;
                setVersionIdOptions(entries.length ? entries : [{ id: "unknown", label: "Unknown" }], entries.length ? entries[entries.length - 1].id : "unknown");
            }
            await refreshSelectedDocument(`Loading ${name} ${selectedVersion}...`);
        });

        versionIdSelect.addEventListener("change", async () => {
            selectedVersionId = versionIdSelect.value;
            await refreshSelectedDocument(`Loading ${name} archive...`);
        });

        versionIdSelect.disabled = true;
        setVersionIdOptions([{ id: "latest", label: "Latest" }], "latest");
        await refreshSelectedDocument(`Loading ${name}...`);
    });
}

async function renderHistoryItem(container, basePath, isCompact = false) {
    const theme = CONFIG[state.theme];
    try {
        const relativePath = basePath.replace(`${CONFIG.archiveBaseUrl}/`, "");
        const meta = await fetchArchiveJson(`${relativePath}/metadata.json`);
        const item = create("div", container, { display: "flex", justifyContent: "space-between", alignItems: "center", padding: isCompact ? "4px 8px" : "8px 12px", borderBottom: isCompact ? "none" : `1px solid ${theme.border}`, fontSize: "11px" });
        const left = create("div", item, { display: "flex", gap: "12px", alignItems: "center" });
        create("div", left, { fontFamily: CONFIG.fonts.mono, color: theme.dim, padding: "1px 5px", backgroundColor: theme.bg, border: `1px solid ${theme.border}`, borderRadius: "3px", fontSize: "10px" }).textContent = meta.commit.substring(0, 7);
        create("div", left, { color: theme.fg, fontSize: "10px" }).textContent = new Date(meta.archived_at * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
        const right = create("div", item, { display: "flex", gap: "6px" });
        if (meta.readme) {
            const btn = create("a", right, { color: theme.dim, textDecoration: "none", padding: "2px 6px", fontSize: "9px", border: `1px solid ${theme.border}`, borderRadius: "3px" });
            btn.href = `${basePath}/${meta.readme}`; btn.target = "_blank"; btn.textContent = "DOCS";
            addHover(btn, { color: theme.dim }, { color: theme.fg, borderColor: theme.fg });
        }
        const dl = create("a", right, { padding: "2px 8px", color: CONFIG.primary, border: `1px solid ${CONFIG.primary}`, borderRadius: "3px", textDecoration: "none", fontWeight: "600", fontSize: "9px" });
        dl.href = `${basePath}/source.tar.gz`; dl.textContent = "DOWNLOAD";
        addHover(dl, { background: "transparent", color: CONFIG.primary }, { background: CONFIG.primary, color: "#fff" });
    } catch(e) {}
}

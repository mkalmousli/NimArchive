let body, root, header, mainContainer, sidebar, contentArea, searchInput, loadingHost, loadingLabel, loadingSubLabel, loadingSpinner, whyOverlay, whyDialog, packageCountLabel;
let loadingToastCount = 0;

function initLayout() {
    if (!document.body) {
        document.documentElement.appendChild(document.createElement("body"));
    }
    body = document.body;
    
    // Global reset
    s(document.documentElement, { margin: "0", padding: "0", overflow: "hidden", height: "100%" });
    s(body, {
        margin: "0",
        padding: "0",
        overflow: "hidden",
        height: "100%",
        width: "100%",
        fontFamily: CONFIG.fonts.sans,
        fontSize: "12px",
        lineHeight: "1.5",
        transition: "background-color 0.2s, color 0.2s"
    });

    root = create("div", body, {
        display: "flex",
        flexDirection: "column",
        height: "100%",
        width: "100%",
        overflow: "hidden"
    });

    loadingHost = create("div", body, {
        position: "fixed",
        right: "16px",
        bottom: "16px",
        zIndex: "1000",
        pointerEvents: "none"
    });

    const loadingPanel = create("div", loadingHost, {
        display: "none",
        minWidth: "220px",
        maxWidth: "320px",
        padding: "10px 12px",
        borderRadius: "12px",
        border: "1px solid",
        boxShadow: "0 14px 36px rgba(0, 0, 0, 0.16)",
        opacity: "0",
        transform: "translateY(6px)",
        transition: "opacity 0.18s ease, transform 0.18s ease"
    });
    const loadingRow = create("div", loadingPanel, {
        display: "flex",
        alignItems: "center",
        gap: "10px"
    });
    loadingSpinner = create("div", loadingRow, {
        width: "18px",
        height: "18px",
        borderRadius: "50%",
        border: "2px solid",
        borderTopColor: "transparent",
        flexShrink: "0",
        animation: "nimarchive-spin 0.75s linear infinite"
    });
    const loadingText = create("div", loadingRow, {
        minWidth: "0",
        display: "flex",
        flexDirection: "column"
    });
    loadingLabel = create("div", loadingText, {
        fontSize: "11px",
        fontWeight: "600",
        letterSpacing: "0.1px",
        marginBottom: "2px",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis"
    });
    loadingSubLabel = create("div", loadingText, {
        fontSize: "10px",
        lineHeight: "1.4"
    });

    const spinStyle = create("style", document.head);
    spinStyle.textContent = "@keyframes nimarchive-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }";

    header = create("div", root, {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "0 12px",
        height: "36px",
        borderBottom: "1px solid",
        flexShrink: "0"
    });

    const headerLeft = create("div", header, { display: "flex", flexDirection: "column", minWidth: "0" });
    const title = create("div", headerLeft, {
        fontWeight: "700",
        fontSize: "13px",
        letterSpacing: "-0.2px"
    });
    title.textContent = "Nim Packages Archive";
    const subtitle = create("div", headerLeft, {
        fontSize: "10px",
        opacity: "0.8",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis"
    });
    subtitle.textContent = "Versioned snapshots, READMEs, licenses, and package history.";
    packageCountLabel = create("div", headerLeft, {
        fontSize: "10px",
        opacity: "0.75",
        marginTop: "2px"
    });
    packageCountLabel.textContent = "0 packages archived";

    const headerRight = create("div", header, { display: "flex", gap: "8px", alignItems: "center" });
    const byline = create("a", headerRight, {
        fontSize: "10px",
        textDecoration: "none",
        whiteSpace: "nowrap"
    });
    byline.href = "https://mkalmousli.dev";
    byline.target = "_blank";
    byline.textContent = "also made by mkalmousli.dev";

    const whyButton = create("button", headerRight, {
        padding: "4px 8px",
        cursor: "pointer",
        border: "1px solid",
        borderRadius: "3px",
        background: "transparent",
        fontSize: "10px"
    });
    whyButton.textContent = "Why?";

    const themeToggle = create("button", headerRight, {
        padding: "4px 8px",
        cursor: "pointer",
        border: "1px solid",
        borderRadius: "3px",
        background: "transparent",
        fontSize: "10px",
        textTransform: "uppercase",
        transition: "all 0.1s"
    });
    themeToggle.textContent = state.theme === "light" ? "Dark" : "Light";
    themeToggle.addEventListener("click", () => {
        state.theme = state.theme === "light" ? "dark" : "light";
        localStorage.setItem("theme", state.theme);
        themeToggle.textContent = state.theme === "light" ? "Dark" : "Light";
        applyTheme();
    });

    whyOverlay = create("div", body, {
        position: "fixed",
        inset: "0",
        display: "none",
        alignItems: "center",
        justifyContent: "center",
        padding: "20px",
        zIndex: "1200"
    });
    whyDialog = create("div", whyOverlay, {
        width: "min(560px, 100%)",
        padding: "18px",
        borderRadius: "10px",
        border: "1px solid"
    });
    const whyTitle = create("div", whyDialog, { fontSize: "16px", fontWeight: "700", marginBottom: "10px" });
    whyTitle.textContent = "Why this archive exists";
    const whyText = create("div", whyDialog, { fontSize: "12px", lineHeight: "1.6" });
    whyText.innerHTML = "This has happened in the Nim community before. Repositories get deleted, tags move, release assets vanish, and old READMEs or licenses become unreachable.<br><br>Part of the problem is structural: there is no strong policy to keep package files available long-term, and the package ecosystem is badly organized in practice. When history is split across the package index, repos, tags, and release pages, losing one layer can make an old package version effectively disappear.<br><br>This archive keeps simple versioned snapshots so Nim package history stays inspectable even when upstream projects disappear. The short version: developers delete repos, and the package ecosystem ends up buried under hierarchy hell.";
    const whyClose = create("button", whyDialog, {
        marginTop: "14px",
        padding: "4px 8px",
        cursor: "pointer",
        border: "1px solid",
        borderRadius: "3px",
        background: "transparent",
        fontSize: "10px"
    });
    whyClose.textContent = "Close";
    const closeWhyDialog = () => { whyOverlay.style.display = "none"; };
    whyButton.addEventListener("click", () => { whyOverlay.style.display = "flex"; });
    whyClose.addEventListener("click", closeWhyDialog);
    whyOverlay.addEventListener("click", (event) => {
        if (event.target === whyOverlay) closeWhyDialog();
    });

    mainContainer = create("div", root, {
        display: "flex",
        flex: "1",
        overflow: "hidden"
    });

    sidebar = create("div", mainContainer, {
        display: "flex",
        flexDirection: "column",
        borderRight: "1px solid",
        width: "240px",
        flexShrink: "0"
    });

    // Search Bar
    const searchContainer = create("div", sidebar, {
        padding: "8px",
        borderBottom: "1px solid"
    });
    searchInput = create("input", searchContainer, {
        width: "calc(100% - 16px)",
        padding: "5px 8px",
        borderRadius: "3px",
        border: "1px solid",
        background: "transparent",
        fontSize: "12px",
        outline: "none"
    });
    searchInput.placeholder = "Search...";
    searchInput.addEventListener("input", (e) => {
        state.searchQuery = e.target.value.toLowerCase();
        renderPackageList();
    });

    contentArea = create("div", mainContainer, {
        flex: "1",
        overflowY: "auto",
        overflowX: "hidden",
        padding: "0" // Padding handled in individual containers
    });

    applyTheme();
    handleResize();
}

function updatePackageCount() {
    if (!packageCountLabel) return;
    const count = Object.keys(state.packages || {}).length;
    packageCountLabel.textContent = `${count.toLocaleString()} packages archived`;
}

function applyTheme() {
    const theme = CONFIG[state.theme];
    s(body, { backgroundColor: theme.bg, color: theme.fg });
    s(header, { borderBottomColor: theme.border });
    s(sidebar, { borderRightColor: theme.border, backgroundColor: theme.surface });
    s(searchInput, { color: theme.fg, borderColor: theme.border });
    if (loadingHost) {
        const panel = loadingHost.firstChild;
        s(panel, {
            backgroundColor: theme.bg,
            borderColor: theme.border
        });
        s(loadingLabel, {
            color: theme.fg
        });
        s(loadingSubLabel, {
            color: theme.dim
        });
        s(loadingSpinner, {
            borderColor: theme.border,
            borderTopColor: CONFIG.primary
        });
    }
    if (whyOverlay) {
        s(whyOverlay, { backgroundColor: state.theme === "light" ? "rgba(255,255,255,0.72)" : "rgba(0,0,0,0.68)" });
        s(whyDialog, { backgroundColor: theme.bg, borderColor: theme.border, color: theme.fg, boxShadow: state.theme === "light" ? "0 14px 50px rgba(0,0,0,0.12)" : "0 14px 50px rgba(0,0,0,0.4)" });
    }
    
    // For specific containers in sidebar
    if (sidebar.firstChild) s(sidebar.firstChild, { borderBottomColor: theme.border });

    const buttons = document.querySelectorAll("button");
    buttons.forEach(btn => {
        s(btn, { 
            color: theme.fg, 
            borderColor: theme.border 
        });
        addHover(btn, 
            { backgroundColor: "transparent", color: theme.fg },
            { backgroundColor: theme.border, color: theme.fg }
        );
    });
    const links = document.querySelectorAll("a");
    links.forEach(link => {
        if (header && header.contains(link)) {
            s(link, { color: theme.dim });
            addHover(link, { color: theme.dim }, { color: CONFIG.primary });
        }
    });

    renderPackageList();
    if (state.selectedPackage) {
        renderPackageDetail(state.selectedPackage);
    }
}

function handleResize() {
    state.width = window.innerWidth;
    state.height = window.innerHeight;

    const theme = CONFIG[state.theme];

    // root already has height/width 100% and overflow hidden

    if (state.width < 768) {
        s(mainContainer, { flexDirection: "column" });
        s(sidebar, { 
            width: "100%", 
            height: "240px", 
            borderRight: "none", 
            borderBottom: `1px solid ${theme.border}`,
            flexShrink: "0"
        });
    } else {
        s(mainContainer, { flexDirection: "row" });
        s(sidebar, { 
            width: "240px", 
            height: "100%", 
            borderBottom: "none", 
            borderRight: `1px solid ${theme.border}`,
            flexShrink: "0"
        });
    }
}

function showLoadingToast(message = "Loading...", details = "Fetching archive data from the NimArchiveData repository") {
    loadingToastCount += 1;
    if (!loadingHost) return;
    const panel = loadingHost.firstChild;
    loadingLabel.textContent = message;
    loadingSubLabel.textContent = details;
    panel.style.display = "block";
    requestAnimationFrame(() => {
        panel.style.opacity = "1";
        panel.style.transform = "translateY(0)";
    });
}

function hideLoadingToast() {
    loadingToastCount = Math.max(0, loadingToastCount - 1);
    if (loadingToastCount > 0 || !loadingHost) return;
    const panel = loadingHost.firstChild;
    panel.style.opacity = "0";
    panel.style.transform = "translateY(6px)";
    window.setTimeout(() => {
        if (loadingToastCount === 0 && panel) {
            panel.style.display = "none";
        }
    }, 180);
}

async function withLoadingToast(message, work, details = "Fetching archive data from the NimArchiveData repository") {
    showLoadingToast(message, details);
    try {
        return await work();
    } finally {
        hideLoadingToast();
    }
}

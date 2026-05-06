const CONFIG = {
    archiveBaseUrl: "https://archive.org/download/NimPackagesArchive",
    corsProxyUrl: "https://api.allorigins.win/raw?url=",
    primary: "#3b82f6",
    light: {
        bg: "#ffffff",
        fg: "#333333",
        surface: "#f3f3f3",
        border: "#e5e5e5",
        dim: "#717171",
        active: "#e0e7ff"
    },
    dark: {
        bg: "#0b0b0b",
        fg: "#cccccc",
        surface: "#181818",
        border: "#2b2b2b",
        dim: "#888888",
        active: "#262626"
    },
    fonts: {
        sans: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
        mono: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace'
    }
};

let state = {
    theme: localStorage.getItem("theme") || "light",
    packages: {},
    searchQuery: "",
    selectedPackage: null,
    width: window.innerWidth,
    height: window.innerHeight
};

function s(el, styles) {
    for (let prop in styles) {
        el.style[prop] = styles[prop];
    }
}

function create(tag, parent, styles = {}) {
    const el = document.createElement(tag);
    if (parent) parent.appendChild(el);
    s(el, { boxSizing: "border-box", ...styles });
    return el;
}

function addHover(el, normalStyles, hoverStyles) {
    el.addEventListener("mouseenter", () => s(el, hoverStyles));
    el.addEventListener("mouseleave", () => s(el, normalStyles));
}

function proxiedArchiveUrl(path) {
    return `${CONFIG.corsProxyUrl}${encodeURIComponent(`${CONFIG.archiveBaseUrl}/${path}`)}`;
}

async function fetchArchiveText(path) {
    const response = await fetch(proxiedArchiveUrl(path));
    if (!response.ok) {
        throw new Error(`Archive fetch failed: ${response.status}`);
    }
    return response.text();
}

async function fetchArchiveJson(path) {
    return JSON.parse(await fetchArchiveText(path));
}

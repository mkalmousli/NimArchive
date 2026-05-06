const CONFIG = {
    archiveBaseUrl: "https://raw.githubusercontent.com/mkalmousli/NimArchiveData/main",
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

async function fetchArchiveText(path) {
    const url = `${CONFIG.archiveBaseUrl}/${path}?t=${Date.now()}`;
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
        throw new Error(`Archive fetch failed: ${response.status}`);
    }
    return response.text();
}

async function fetchArchiveJson(path) {
    return JSON.parse(await fetchArchiveText(path));
}

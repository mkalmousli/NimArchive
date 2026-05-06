(function() {
    async function fetchData() {
        try {
            await withLoadingToast("Loading packages...", async () => {
                state.packages = await fetchArchiveJson("index.json");
                updatePackageCount();
                renderPackageList();
                if (!state.selectedPackage) {
                    const packageNames = Object.keys(state.packages);
                    if (packageNames.length > 0) {
                        const randomName = packageNames[Math.floor(Math.random() * packageNames.length)];
                        state.selectedPackage = randomName;
                        renderPackageList();
                        await renderPackageDetail(randomName);
                    }
                }
            });
        } catch (e) {
            console.error("Failed to fetch packages", e);
        }
    }

    window.addEventListener("resize", handleResize);
    initLayout();
    fetchData();
})();

/** @odoo-module **/
import { registry } from "@web/core/registry";

const solvitaskTheme = {
    start() {
        const apply = () => {
            const brand = document.querySelector(".o_menu_brand");

            const isSolvitask =
                brand?.textContent.trim() === "SolviTask";

            if (
                document.body.classList.contains("o_solvitask_theme")
                !== isSolvitask
            ) {
                document.body.classList.toggle(
                    "o_solvitask_theme",
                    isSolvitask
                );
            }
        };

        apply();

        const observer = new MutationObserver(apply);

        observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true,
        });
    },
};

registry.category("services").add("solvitask_theme", solvitaskTheme);
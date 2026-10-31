import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NAV_ITEMS } from "@/app/nav";
import { renderApp } from "@/test/render";

describe("application shell", () => {
  it("lists every page in the main navigation", async () => {
    renderApp("/");
    const nav = screen.getByRole("navigation", { name: "Navigation principale" });
    const links = within(nav).getAllByRole("link");
    expect(links).toHaveLength(NAV_ITEMS.length);
    expect(within(nav).getByRole("link", { name: "Accueil" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    // the page's code loads on first visit
    await waitFor(() => expect(document.title).toBe("Accueil - CoTraffic"));
  });

  it("marks the current page and navigates on click", async () => {
    const { user, router } = renderApp("/");
    const nav = screen.getByRole("navigation", { name: "Navigation principale" });
    await user.click(within(nav).getByRole("link", { name: "Paramètres" }));

    expect(router.state.location.pathname).toBe("/settings");
    expect(await screen.findByRole("heading", { level: 1, name: "Paramètres" })).toBeVisible();
    expect(within(nav).getByRole("link", { name: "Paramètres" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(document.title).toBe("Paramètres - CoTraffic");
  });

  it("shows a not-found page for an unknown address", async () => {
    renderApp("/nowhere");
    expect(await screen.findByRole("heading", { name: "Page introuvable" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Retour à l'accueil" })).toHaveAttribute("href", "/");
  });

  it("opens the command palette with Ctrl+K, finds a page and goes there", async () => {
    const { user, router } = renderApp("/settings");
    await screen.findByRole("heading", { level: 1, name: "Paramètres" });

    await user.keyboard("{Control>}k{/Control}");
    const palette = await screen.findByRole("dialog", { name: "Palette de commandes" });
    const input = within(palette).getByRole("combobox", { name: "Palette de commandes" });
    expect(input).toHaveFocus();

    // accents and case do not matter
    await user.type(input, "robustesse");
    const options = within(palette).getAllByRole("option");
    expect(options[0]).toHaveTextContent("Robustesse et généralisation");
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Enter}");

    expect(router.state.location.pathname).toBe("/robustness");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens the assistant from the palette, and Escape closes the palette", async () => {
    const { user } = renderApp("/settings");
    await screen.findByRole("heading", { level: 1 });

    await user.keyboard("{Control>}k{/Control}");
    await screen.findByRole("dialog", { name: "Palette de commandes" });
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.keyboard("{Control>}k{/Control}");
    const palette = await screen.findByRole("dialog", { name: "Palette de commandes" });
    // a fresh search on each opening
    const input = within(palette).getByRole("combobox");
    expect(input).toHaveValue("");
    await user.type(input, "assistant");
    await user.keyboard("{ArrowDown}");
    const selected = within(palette)
      .getAllByRole("option")
      .find((o) => o.getAttribute("aria-selected") === "true");
    expect(selected).toHaveTextContent("Ouvrir l'assistant");
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("dialog", { name: "Assistant" })).toBeVisible();
  });

  it("collapses the sidebar but keeps accessible link names", async () => {
    const { user } = renderApp("/");
    await user.click(screen.getByRole("button", { name: "Réduire le menu" }));

    expect(screen.getByRole("button", { name: "Déplier le menu" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.getByRole("link", { name: "Carte en direct" })).toBeInTheDocument();
  });
});

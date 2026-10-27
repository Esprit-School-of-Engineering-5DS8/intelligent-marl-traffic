import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NAV } from "@/app/nav";
import { renderApp } from "@/test/render";

describe("application shell", () => {
  it("lists every page in the main navigation", async () => {
    renderApp("/");
    const nav = screen.getByRole("navigation", { name: "Navigation principale" });
    const links = within(nav).getAllByRole("link");
    expect(links).toHaveLength(NAV.flatMap((g) => g.items).length);
    expect(await screen.findByRole("heading", { level: 1, name: "Vue d'ensemble" })).toBeVisible();
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
    expect(document.title).toBe("Paramètres - KEMETRA");
  });

  it("shows a not-found page for an unknown address", async () => {
    renderApp("/nowhere");
    expect(await screen.findByRole("heading", { name: "Page introuvable" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Retour à la vue d'ensemble" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("opens the assistant panel with Ctrl+K and closes it with Escape", async () => {
    const { user } = renderApp("/");
    await screen.findByRole("heading", { level: 1 });

    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByRole("dialog", { name: "Assistant" })).toBeVisible();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
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

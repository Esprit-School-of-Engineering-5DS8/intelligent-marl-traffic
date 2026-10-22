import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";

function Fragile({ broken }: { broken: boolean }) {
  if (broken) throw new Error("boom");
  return <p>widget ok</p>;
}

function Harness() {
  const [broken, setBroken] = useState(true);
  return (
    <>
      <button type="button" onClick={() => setBroken(false)}>
        repair
      </button>
      <ErrorBoundary>
        <Fragile broken={broken} />
      </ErrorBoundary>
    </>
  );
}

describe("ErrorBoundary", () => {
  it("contains a crash and recovers on retry", async () => {
    const silence = vi.spyOn(console, "error").mockImplementation(() => {});
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.getByRole("alert")).toHaveTextContent("Cette partie de l'écran");
    // the rest of the screen still works
    await user.click(screen.getByRole("button", { name: "repair" }));
    await user.click(screen.getByRole("button", { name: "Réessayer" }));

    expect(screen.getByText("widget ok")).toBeVisible();
    silence.mockRestore();
  });
});

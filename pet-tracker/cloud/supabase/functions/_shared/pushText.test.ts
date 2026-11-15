import { assertEquals } from "jsr:@std/assert@1";
import { pushText } from "./pushText.ts";

Deno.test("push text follows the reader's language", () => {
  const row = { kind: "zone_exit", title: "Minoes left Home", body: "x", meta: { zone: "Thuis" } };
  assertEquals(pushText(row, "Minoes", "nl").title, "Minoes is Thuis uit");
  assertEquals(pushText({ ...row, meta: { zone: "Home" } }, "Minoes", "en").title, "Minoes left Home");
  assertEquals(pushText({ kind: "low_battery", title: "t", body: "b", meta: { battery: 15 } }, "Pluis", "en").body, "Battery at 15%. Charge it soon.");
});

Deno.test("unknown kinds keep the database text", () => {
  assertEquals(pushText({ kind: "something_new", title: "T", body: "B" }, "Minoes", "nl"), { title: "T", body: "B" });
});

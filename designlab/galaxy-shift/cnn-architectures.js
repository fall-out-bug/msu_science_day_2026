// Frozen architecture grammar for the offline CNN experiment table.
(function (root) {
  "use strict";
  const tails = [["r"], ["bn", "r"], ["r", "bn"], ["d", "r"], ["r", "d"], ["bn", "d", "r"], ["bn", "r", "d"], ["d", "bn", "r"], ["d", "r", "bn"], ["r", "bn", "d"], ["r", "d", "bn"]];
  const names = { r: "ReLU", bn: "BatchNorm", d: "Dropout" };
  const configurations = Object.freeze([1, 2].flatMap((depth) => tails.map((tail) => Object.freeze({ id: `d${depth}-${tail.join("-")}`, depth, tail: Object.freeze([...tail]), label: `${depth === 1 ? "Одна свёртка" : "Две свёртки"}: ${tail.map((item) => names[item]).join(" → ")}` }))));
  const byId = new Map(configurations.map((configuration) => [configuration.id, configuration]));
  function get(id) { return byId.get(id) || null; }
  function find(depth, tail) { return get(`d${depth}-${Array.from(tail).join("-")}`); }
  root.GalaxyArchitectures = Object.freeze({ configurations, get, find });
})(globalThis);

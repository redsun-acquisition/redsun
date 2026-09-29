// Builds an install command from the buttons of a ".install-table".
//
// The page holds the choices, this script holds none. A row marked
// data-role="command" gives the start of the command, a row marked
// data-role="extra" gives extras. One button of a row is chosen at a time,
// unless the row has data-multiple, where each button is switched on and off.

function setUpInstallTable(table) {
  if (table.dataset.ready) return;
  table.dataset.ready = "true";

  const output = table.querySelector(".install-command");
  const rows = table.querySelectorAll(".install-row[data-role]");

  const update = () => {
    let command = "";
    const extras = [];
    rows.forEach((row) => {
      row.querySelectorAll('button[aria-pressed="true"]').forEach((button) => {
        if (row.dataset.role === "command") command = button.dataset.value;
        else if (button.dataset.value) extras.push(button.dataset.value);
      });
    });
    const name = table.dataset.package;
    const target = extras.length ? `"${name}[${extras.join(",")}]"` : name;
    output.textContent = [command, target].filter(Boolean).join(" ");
  };

  rows.forEach((row) => {
    const buttons = row.querySelectorAll("button");
    const multiple = "multiple" in row.dataset;
    buttons.forEach((button, index) => {
      button.setAttribute("aria-pressed", String(!multiple && index === 0));
      button.addEventListener("click", () => {
        if (multiple) {
          const pressed = button.getAttribute("aria-pressed") === "true";
          button.setAttribute("aria-pressed", String(!pressed));
        } else {
          buttons.forEach((other) =>
            other.setAttribute("aria-pressed", String(other === button)),
          );
        }
        update();
      });
    });
  });

  const copy = table.querySelector(".install-copy");
  // the clipboard exists on a page served over HTTPS or from this machine
  if (copy && navigator.clipboard) {
    copy.hidden = false;
    copy.addEventListener("click", () => {
      navigator.clipboard
        .writeText(output.textContent)
        .then(() => {
          copy.textContent = "Copied";
          setTimeout(() => (copy.textContent = "Copy"), 1500);
        })
        .catch(() => (copy.hidden = true));
    });
  }

  update();
}

function setUpInstallTables() {
  document.querySelectorAll(".install-table").forEach(setUpInstallTable);
}

// the theme announces each page it shows; without it, the page loads once
if (typeof document$ !== "undefined") document$.subscribe(setUpInstallTables);
else if (document.readyState === "loading")
  document.addEventListener("DOMContentLoaded", setUpInstallTables);
else setUpInstallTables();

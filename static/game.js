// Without JavaScript the named form still submits normally.
const setup = document.querySelector("#setup-form");
if (setup) {
  const showNames = () => {
    const count = Number(setup.elements.humans.value);
    for (const seat of setup.querySelectorAll("[data-seat]")) {
      const active = Number(seat.dataset.seat) <= count;
      const input = seat.querySelector("input");
      seat.hidden = !active;
      input.disabled = !active;
      input.required = active;
    }
  };
  setup.addEventListener("change", showNames);
  showNames();
}

// A page restored from browser history must ask the server for the current screen.
window.addEventListener("pageshow", (event) => {
  if (event.persisted) window.location.reload();
});

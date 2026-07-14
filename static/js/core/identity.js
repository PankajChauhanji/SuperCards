// Stable identity that survives refreshes — the key to reconnection.
// user_id is generated once and kept in localStorage; the server keys players
// by it (never by the volatile socket id).
(function () {
  function makeId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "u-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  window.Identity = {
    userId() {
      let id = localStorage.getItem("ss_user_id");
      if (!id) {
        id = makeId();
        localStorage.setItem("ss_user_id", id);
      }
      return id;
    },
    name(value) {
      if (value !== undefined) {
        localStorage.setItem("ss_name", value);
        return value;
      }
      return localStorage.getItem("ss_name") || "";
    },
  };
})();

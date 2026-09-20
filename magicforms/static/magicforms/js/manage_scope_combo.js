/**
 * Superuser organization scope: single <select>, submits on change (no Apply button).
 */
(function () {
  var form = document.getElementById("mf-manage-scope-form");
  var select = document.getElementById("mf-scope-select");
  if (!form || !select) return;

  select.addEventListener("change", function () {
    form.submit();
  });
})();

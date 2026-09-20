/**
 * Sync native color wells with Entity theme hex text fields (organization form).
 */
(function () {
  function isHex7(v) {
    return /^#[0-9A-Fa-f]{6}$/.test(String(v || "").trim());
  }

  document.querySelectorAll(".mf-theme-color-picker").forEach(function (picker) {
    var hexId = picker.getAttribute("data-mf-hex-target");
    if (!hexId) return;
    var hex = document.getElementById(hexId);
    if (!hex) return;
    var optional = picker.getAttribute("data-mf-optional") === "1";
    var emptySwatch = "#ffffff";

    function readHex() {
      return String(hex.value || "").trim();
    }

    function pickerFromHex() {
      var v = readHex();
      if (isHex7(v)) {
        picker.value = v.toLowerCase();
        return;
      }
      if (optional) {
        picker.value = emptySwatch;
        return;
      }
      picker.value = "#3b5f8f";
    }

    pickerFromHex();

    picker.addEventListener("input", function () {
      hex.value = picker.value;
    });
    picker.addEventListener("change", function () {
      hex.value = picker.value;
    });

    hex.addEventListener("input", function () {
      var v = readHex();
      if (isHex7(v)) {
        picker.value = v.toLowerCase();
      } else if (optional) {
        picker.value = emptySwatch;
      } else if (!v) {
        picker.value = "#3b5f8f";
      }
    });
  });
})();

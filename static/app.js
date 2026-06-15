const dropZone = document.querySelector("#dropZone");
const imageInput = document.querySelector("#imageInput");
const fileName = document.querySelector("#fileName");
const uploadForm = document.querySelector("#uploadForm");
const submitButton = document.querySelector("#submitButton");
const dropContent = document.querySelector("#dropContent");
const uploadPreview = document.querySelector("#uploadPreview");
const previewImage = document.querySelector("#previewImage");
const results = document.querySelector("#results");
const reportForm = document.querySelector("#reportForm");
const reportButton = document.querySelector("#reportButton");
const report = document.querySelector("#report");

function showPreview(file) {
  if (!file || !uploadPreview || !previewImage || !dropContent) {
    return;
  }

  previewImage.src = URL.createObjectURL(file);
  fileName.textContent = file.name;
  dropContent.hidden = true;
  uploadPreview.hidden = false;
}

if (dropZone && imageInput && fileName) {
  dropZone.addEventListener("click", () => imageInput.click());

  dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragging");
  });

  dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");

    if (event.dataTransfer.files.length) {
      imageInput.files = event.dataTransfer.files;
      showPreview(event.dataTransfer.files[0]);
    }
  });

  imageInput.addEventListener("change", () => {
    if (imageInput.files.length) {
      showPreview(imageInput.files[0]);
    }
  });
}

if (uploadForm && submitButton) {
  uploadForm.addEventListener("submit", () => {
    submitButton.textContent = "Scanning image...";
    submitButton.disabled = true;
  });
}

if (reportForm && reportButton) {
  reportForm.addEventListener("submit", () => {
    reportButton.textContent = "Generating...";
    reportButton.disabled = true;
  });
}

if (results) {
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

if (report) {
  report.scrollIntoView({ behavior: "smooth", block: "start" });
}

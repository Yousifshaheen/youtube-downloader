"use strict";

const urlForm = document.getElementById("url-form");
const urlInput = document.getElementById("url-input");
const fetchBtn = document.getElementById("fetch-btn");
const fetchError = document.getElementById("fetch-error");

const loader = document.getElementById("loader");
const videoCard = document.getElementById("video-card");

const videoThumbnail = document.getElementById("video-thumbnail");
const videoTitle = document.getElementById("video-title");
const videoChannel = document.getElementById("video-channel");
const videoDuration = document.getElementById("video-duration");
const videoDate = document.getElementById("video-date");
const videoViews = document.getElementById("video-views");

const qualitySelect = document.getElementById("quality-select");
const formatSelect = document.getElementById("format-select");
const downloadBtn = document.getElementById("download-btn");
const downloadError = document.getElementById("download-error");
const downloadSuccess = document.getElementById("download-success");

let currentUrl = "";

function showElement(el) {
  el.hidden = false;
}

function hideElement(el) {
  el.hidden = true;
}

function setErrorMessage(el, message) {
  el.textContent = message;
  showElement(el);
}

function clearMessages() {
  hideElement(fetchError);
  hideElement(downloadError);
  hideElement(downloadSuccess);
}

function formatViews(views) {
  if (views === null || views === undefined) {
    return "Unknown";
  }
  return new Intl.NumberFormat("en-US").format(views);
}

function qualityLabel(height) {
  if (height === 2160) return "2160p (4K)";
  if (height === 4320) return "4320p (8K)";
  return `${height}p`;
}

function populateQualityOptions(qualities) {
  qualitySelect.innerHTML = "";

  if (!qualities || qualities.length === 0) {
    const option = document.createElement("option");
    option.value = "best";
    option.textContent = "Best available";
    qualitySelect.appendChild(option);
    return;
  }

  qualities
    .slice()
    .reverse()
    .forEach((height) => {
      const option = document.createElement("option");
      option.value = String(height);
      option.textContent = qualityLabel(height);
      qualitySelect.appendChild(option);
    });
}

function updateQualityAvailability() {
  qualitySelect.disabled = formatSelect.value === "mp3";
}

async function handleFetchVideo(event) {
  event.preventDefault();
  clearMessages();
  hideElement(videoCard);

  const url = urlInput.value.trim();
  if (!url) {
    return;
  }

  currentUrl = url;
  fetchBtn.disabled = true;
  showElement(loader);

  try {
    const response = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    const payload = await response.json();

    if (!response.ok || !payload.success) {
      throw new Error(payload.error || "Failed to fetch video information.");
    }

    const data = payload.data;
    videoThumbnail.src = data.thumbnail;
    videoTitle.textContent = data.title;
    videoChannel.textContent = data.channel;
    videoDuration.textContent = data.duration;
    videoDate.textContent = data.upload_date;
    videoViews.textContent = formatViews(data.views);

    populateQualityOptions(data.qualities);
    updateQualityAvailability();

    showElement(videoCard);
  } catch (error) {
    setErrorMessage(fetchError, error.message);
  } finally {
    fetchBtn.disabled = false;
    hideElement(loader);
  }
}

async function handleDownload() {
  clearMessages();

  if (!currentUrl) {
    return;
  }

  const quality = qualitySelect.value;
  const format = formatSelect.value;

  downloadBtn.disabled = true;
  downloadBtn.textContent = "Downloading...";

  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: currentUrl, quality, format }),
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "Download failed. Please try again.");
    }

    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : `download.${format}`;

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(objectUrl);

    downloadSuccess.textContent = "Download complete!";
    showElement(downloadSuccess);
  } catch (error) {
    setErrorMessage(downloadError, error.message);
  } finally {
    downloadBtn.disabled = false;
    downloadBtn.textContent = "Download";
  }
}

urlForm.addEventListener("submit", handleFetchVideo);
formatSelect.addEventListener("change", updateQualityAvailability);
downloadBtn.addEventListener("click", handleDownload);

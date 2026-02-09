// SKH eSign - Apps Script Bridge
// Deploy as Web App:
//   Execute as: Me
//   Who has access: Anyone
//
// IMPORTANT:
// Apps Script Web Apps don't reliably expose request headers.
// Streamlit MUST include api_key in JSON body (POST) and query (GET download).

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function _apiKey_() {
  var props = PropertiesService.getScriptProperties();
  return props.getProperty("API_KEY") || "";
}

function doGet(e) {
  var action = (e && e.parameter && e.parameter.action) ? e.parameter.action : "ping";
  if (action === "ping") {
    return _json({ ok: true, message: "pong" });
  }

  if (action === "download") {
    var expected = _apiKey_();
    if (!expected) return _json({ ok: false, error: "API_KEY not set in Script Properties" });

    var got = (e.parameter && e.parameter.api_key) ? e.parameter.api_key : "";
    if (got !== expected) return _json({ ok: false, error: "Unauthorized" });

    var fileId = e.parameter.fileId;
    if (!fileId) return _json({ ok: false, error: "Missing fileId" });

    try {
      var file = DriveApp.getFileById(fileId);
      var blob = file.getBlob();
      var b64 = Utilities.base64Encode(blob.getBytes());
      return _json({ ok: true, mimeType: blob.getContentType(), data_base64: b64 });
    } catch (err) {
      return _json({ ok: false, error: String(err) });
    }
  }

  return _json({ ok: false, error: "Unknown action" });
}

function doPost(e) {
  try {
    var body = {};
    if (e && e.postData && e.postData.contents) {
      body = JSON.parse(e.postData.contents);
    }

    var expected = _apiKey_();
    if (!expected) return _json({ ok: false, error: "API_KEY not set in Script Properties" });

    if ((body.api_key || "") !== expected) {
      return _json({ ok: false, error: "Unauthorized" });
    }

    if ((body.action || "") !== "upload") {
      return _json({ ok: false, error: "Unknown action" });
    }

    var folderId = body.folderId;
    var filename = body.filename || ("signature_" + new Date().getTime() + ".png");
    var mimeType = body.mimeType || "image/png";
    var dataB64 = body.data_base64;

    if (!folderId) return _json({ ok: false, error: "Missing folderId" });
    if (!dataB64) return _json({ ok: false, error: "Missing data_base64" });

    // size guard (base64 length)
    if (dataB64.length > 800000) {
      return _json({ ok: false, error: "Payload too large" });
    }

    var bytes = Utilities.base64Decode(dataB64);
    var blob = Utilities.newBlob(bytes, mimeType, filename);

    var folder = DriveApp.getFolderById(folderId);
    var file = folder.createFile(blob);

    return _json({ ok: true, fileId: file.getId() });

  } catch (err) {
    return _json({ ok: false, error: String(err) });
  }
}

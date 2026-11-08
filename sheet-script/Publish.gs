/**
 * "Seating" menu for the wedding guest list Google Sheet.
 *
 *   Publish to website now         rebuilds the Find Your Table page (live in about a minute)
 *   Turn on automatic publishing   publishes by itself a few minutes after edits stop
 *
 * It asks GitHub to run the "Publish table finder" job, the same as clicking
 * "Run workflow" on GitHub. It needs a GitHub token saved as the script property
 * GITHUB_TOKEN (Extensions > Apps Script > Project Settings > Script properties).
 */
const REPO = 'emergingTechExplorer/sachini-lakshantha';
const WORKFLOW = 'publish.yml';
const QUIET_MINUTES = 2; // automatic publishing waits this long after the last edit

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Seating')
    .addItem('Publish to website now', 'publishNow')
    .addSeparator()
    .addItem('Turn on automatic publishing', 'turnOnAutoPublish')
    .addItem('Turn off automatic publishing', 'turnOffAutoPublish')
    .addToUi();
}

function publishNow() {
  const result = requestPublish_();
  if (result.ok) {
    SpreadsheetApp.getActive().toast('The website will show these changes in about a minute.', 'Publishing', 8);
  } else {
    const ui = SpreadsheetApp.getUi();
    ui.alert("Couldn't publish", result.message, ui.ButtonSet.OK);
  }
}

function turnOnAutoPublish() {
  removeAutoPublishTriggers_();
  ScriptApp.newTrigger('recordEdit').forSpreadsheet(SpreadsheetApp.getActive()).onEdit().create();
  ScriptApp.newTrigger('publishIfEdited').timeBased().everyMinutes(5).create();
  SpreadsheetApp.getActive().toast(
    'From now on, the website updates a few minutes after you stop editing.', 'Automatic publishing on', 8);
}

function turnOffAutoPublish() {
  removeAutoPublishTriggers_();
  SpreadsheetApp.getActive().toast('Use Seating > Publish to website now after editing.', 'Automatic publishing off', 8);
}

// Runs on every edit while automatic publishing is on: just notes the time.
function recordEdit() {
  PropertiesService.getScriptProperties().setProperty('LAST_EDIT', String(Date.now()));
}

// Runs every 5 minutes while automatic publishing is on.
function publishIfEdited() {
  const props = PropertiesService.getScriptProperties();
  const lastEdit = Number(props.getProperty('LAST_EDIT') || 0);
  const lastPublish = Number(props.getProperty('LAST_PUBLISH') || 0);
  const quietFor = Date.now() - lastEdit;
  if (lastEdit > lastPublish && quietFor >= QUIET_MINUTES * 60 * 1000) {
    const result = requestPublish_();
    if (!result.ok) console.error(result.message);
  }
}

function requestPublish_() {
  const props = PropertiesService.getScriptProperties();
  const token = (props.getProperty('GITHUB_TOKEN') || '').trim();
  if (!token) {
    return { ok: false, message: 'No GitHub token is saved yet. In Extensions > Apps Script, open Project Settings and add a script property named GITHUB_TOKEN.' };
  }
  const response = UrlFetchApp.fetch(
    'https://api.github.com/repos/' + REPO + '/actions/workflows/' + WORKFLOW + '/dispatches',
    {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
      payload: JSON.stringify({ ref: 'main' }),
      muteHttpExceptions: true,
    });
  const code = response.getResponseCode();
  if (code === 204) {
    props.setProperty('LAST_PUBLISH', String(Date.now()));
    return { ok: true };
  }
  if (code === 401) {
    return { ok: false, message: 'GitHub rejected the token. It may have expired: create a new one and replace GITHUB_TOKEN in Project Settings.' };
  }
  if (code === 403 || code === 404) {
    return { ok: false, message: "The token can't run the publish job. Check that it has access to the sachini-lakshantha repository with Actions set to 'Read and write'." };
  }
  return { ok: false, message: 'GitHub answered ' + code + ': ' + response.getContentText().slice(0, 200) };
}

function removeAutoPublishTriggers_() {
  ScriptApp.getProjectTriggers()
    .filter((t) => ['recordEdit', 'publishIfEdited'].includes(t.getHandlerFunction()))
    .forEach((t) => ScriptApp.deleteTrigger(t));
}

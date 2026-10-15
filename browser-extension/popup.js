const input = document.getElementById('token');
const status = document.getElementById('status');
chrome.storage.local.get('windowrift_token', values => { input.value = values.windowrift_token || ''; });

async function activeTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  if (!tab || !tab.id || !/^https?:/.test(tab.url || ''))
    throw new Error('Open a normal http(s) page first. Chrome internal pages are unsupported.');
  return tab;
}

document.getElementById('enable').addEventListener('click', async () => {
  const token = input.value.trim();
  if (!token) { status.textContent = 'Copy a session token from WindowRift first.'; return; }
  try {
    const tab = await activeTab();
    await chrome.storage.local.set({ windowrift_token: token });
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
    await chrome.tabs.sendMessage(tab.id, { type: 'WINDOWRIFT_START', token });
    status.textContent = 'Enabled on this tab. Drag a sprite over page content.';
  } catch (err) { status.textContent = String(err.message || err); }
});

document.getElementById('reset').addEventListener('click', async () => {
  try {
    const tab = await activeTab();
    await chrome.tabs.sendMessage(tab.id, { type: 'WINDOWRIFT_RESET' });
    status.textContent = 'Page styling restored and disconnected.';
  } catch (err) { status.textContent = String(err.message || err); }
});

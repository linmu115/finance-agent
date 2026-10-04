// Shared selectors for the project -> conversation sidebar.
async function selectedProject(page) {
  return page.locator('.project-group.selected').getAttribute('data-project-id');
}
async function chooseProject(page, id) {
  const group = page.locator('.project-group').filter({ has: page.locator(`[aria-controls="project-chats-${id}"]`) });
  const toggle = group.locator('.project-toggle');
  if (await selectedProject(page) !== id || await toggle.getAttribute('aria-expanded') !== 'true') await toggle.click();
  // Selecting an already expanded, inactive project collapses it; open it again.
  if (await toggle.getAttribute('aria-expanded') !== 'true') await toggle.click();
}
module.exports = { selectedProject, chooseProject };

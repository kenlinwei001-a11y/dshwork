// Host half: the panel is purely client-side (File System Access API + iframe),
// so there are no host tools or routes to register. The package still carries a
// valid Cordis plugin so the profile bundle can load it.
export const name = 'workdsh-plugin-craftcad-panel';

export function apply() {}

/**
 * featureFlags.js — Frontend feature flag definitions (fallback).
 */

const ROLE_HIERARCHY = { reader: 0, maintainer: 1, admin: 2 };

const FLAG_DEFS = {
    'tests.create':       'maintainer',
    'tests.delete':       'maintainer',
    'tests.run':          'reader',
    'tests.stop':         'reader',
    'configs.create':     'maintainer',
    'configs.delete':     'maintainer',
    'environments.create':'maintainer',
    'environments.delete':'admin',
    'storage.clear':      'admin',
    'cleanup.run':        'maintainer',
    'results.export':     'reader',
    'results.notes':      'maintainer',
};

export function getFlagsForRole(role) {
    const userLevel = ROLE_HIERARCHY[role] ?? -1;
    return Object.entries(FLAG_DEFS)
        .filter(([, minRole]) => userLevel >= (ROLE_HIERARCHY[minRole] ?? 999))
        .map(([flag]) => flag);
}

export function checkFlag(flag, role) {
    const minRole = FLAG_DEFS[flag];
    if (!minRole) return false;
    return (ROLE_HIERARCHY[role] ?? -1) >= (ROLE_HIERARCHY[minRole] ?? 999);
}

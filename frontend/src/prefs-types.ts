import type { Dispatch, SetStateAction } from 'react';
import type { UserPrefs } from './types';

export type PrefsTuple = readonly [UserPrefs, Dispatch<SetStateAction<UserPrefs>>];

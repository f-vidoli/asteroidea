import type { ScreenTarget } from '../../core/types';
import { SCREEN_TARGETS } from '../../core/types';

export interface NavBar {
  element: HTMLElement;
  setActive(target: ScreenTarget): void;
}

export function createNav(host: HTMLElement, onSelect: (target: ScreenTarget) => void): NavBar {
  const element = document.createElement('nav');
  element.className = 'bottom-nav';
  const buttons = new Map<ScreenTarget, HTMLButtonElement>();

  for (const [target, label] of [
    [SCREEN_TARGETS.MAIN, 'Main'],
    [SCREEN_TARGETS.FEED, 'Feed'],
    [SCREEN_TARGETS.SETTINGS, 'Settings'],
    [SCREEN_TARGETS.MANAGER, 'Plugins'],
  ] as const) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.dataset['screen'] = target;
    button.addEventListener('click', () => {
      setActive(target);
      onSelect(target);
    });
    buttons.set(target, button);
    element.append(button);
  }

  const setActive = (target: ScreenTarget): void => {
    for (const [name, button] of buttons) button.dataset['active'] = String(name === target);
  };

  host.append(element);
  setActive(SCREEN_TARGETS.MAIN);
  return { element, setActive };
}

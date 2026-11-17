export interface ConfirmDialogOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
}

export function confirmDialog(options: ConfirmDialogOptions): Promise<boolean> {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'dialog-overlay';
    const dialog = document.createElement('div');
    dialog.className = 'dialog';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');

    const title = document.createElement('h2');
    title.textContent = options.title;
    const message = document.createElement('p');
    message.textContent = options.message;
    const actions = document.createElement('div');
    actions.className = 'dialog-actions';

    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = options.cancelLabel ?? 'Cancel';
    const confirm = document.createElement('button');
    confirm.type = 'button';
    confirm.className = 'dialog-confirm';
    confirm.textContent = options.confirmLabel ?? 'Confirm';

    let finished = false;
    const close = (result: boolean): void => {
      if (finished) return;
      finished = true;
      document.removeEventListener('keydown', onKeyDown);
      overlay.remove();
      resolve(result);
    };
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') close(false);
    };

    cancel.addEventListener('click', () => close(false));
    confirm.addEventListener('click', () => close(true));
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) close(false);
    });
    document.addEventListener('keydown', onKeyDown);

    actions.append(cancel, confirm);
    dialog.append(title, message, actions);
    overlay.append(dialog);
    document.body.append(overlay);
    confirm.focus();
  });
}

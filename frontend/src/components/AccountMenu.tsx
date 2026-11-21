import { useEffect, useRef, useState } from "react";
import { UserIcon } from "./icons";

interface Props {
  email: string;
  onSignOut: () => void;
}

export function AccountMenu({ email, onSignOut }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="account" ref={rootRef}>
      <button
        type="button"
        className="icon-button"
        aria-label="Compte"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((v) => !v)}
      >
        <UserIcon />
      </button>
      {open && (
        <div className="account__menu">
          <p className="account__email">{email}</p>
          <button type="button" className="account__item" onClick={onSignOut}>
            Se déconnecter
          </button>
        </div>
      )}
    </div>
  );
}

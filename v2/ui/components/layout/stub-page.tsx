import { ReactNode } from "react";

type Props = {
  title: string;
  description: string;
  children?: ReactNode;
};

export function StubPage({ title, description, children }: Props) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-6">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-sm text-zinc-400">{description}</p>
      {children ? <div className="mt-6">{children}</div> : null}
    </div>
  );
}


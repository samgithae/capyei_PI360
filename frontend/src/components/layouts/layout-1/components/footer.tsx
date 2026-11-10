import { generalSettings } from '@/config/general.config';

export function Footer() {
  return (
    <footer className="footer">
      <div className="container-fluid">
        <div className="flex justify-between items-center gap-3 py-5 text-sm">
          <span className="text-muted-foreground">
            {new Date().getFullYear()} &copy; {generalSettings.owner}
          </span>
          <span className="text-muted-foreground">
            {generalSettings.appName}
          </span>
        </div>
      </div>
    </footer>
  );
}

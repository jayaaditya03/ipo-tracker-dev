// angular import
import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

// project import
import { AuthService } from './core/auth.service';
import { SpinnerComponent } from './theme/shared/components/spinner/spinner.component';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  imports: [RouterOutlet, SpinnerComponent]
})
export class AppComponent {
  // public props
  title = 'IPO-PRO';

  constructor() {
    // Refresh the cached user so fields added since sign-in (is_staff) are current.
    const auth = inject(AuthService);
    if (auth.isLoggedIn()) auth.loadMe().subscribe({ error: () => undefined });
  }
}

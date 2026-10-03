// angular import
import { Component, computed, inject } from '@angular/core';

// project import
import { SharedModule } from 'src/app/theme/shared/shared.module';
import { AuthService } from 'src/app/core/auth.service';

// icon
import { IconService } from '@ant-design/icons-angular';
import { LogoutOutline } from '@ant-design/icons-angular/icons';

/** Signed-in user's menu: who you are, and sign out. */
@Component({
  selector: 'app-nav-right',
  imports: [SharedModule],
  templateUrl: './nav-right.component.html',
  styleUrls: ['./nav-right.component.scss']
})
export class NavRightComponent {
  protected auth = inject(AuthService);

  displayName = computed(() => this.auth.user()?.full_name || this.auth.user()?.email || '');
  initials = computed(() => {
    const name = this.displayName().split('@')[0];
    const parts = name.split(/[\s._-]+/).filter(Boolean);
    return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '?';
  });

  constructor() {
    inject(IconService).addIcon(LogoutOutline);
  }
}

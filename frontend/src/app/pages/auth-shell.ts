import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

/** Mantis auth layout (centred card on the brand background), shared by login and register. */
@Component({
  selector: 'app-auth-shell',
  imports: [RouterLink],
  template: `
    <div class="auth-main">
      <div class="auth-wrapper v3">
        <div class="auth-form">
          <div class="auth-header">
            <a routerLink="/" class="b-brand d-flex align-items-center gap-2 text-decoration-none">
              <img src="assets/images/logo-mark.svg" alt="" width="34" height="34" />
              <span class="brand-name">IPO-PRO</span>
            </a>
          </div>
          <div class="card my-5">
            <div class="card-body">
              <div class="d-flex justify-content-between align-items-end mb-4">
                <h3 class="mb-0"><b>{{ heading() }}</b></h3>
                <a [routerLink]="altLink()" class="link-primary">{{ altText() }}</a>
              </div>
              <ng-content />
            </div>
          </div>
          <div class="auth-footer">
            <p class="m-0 text-muted">Track IPO applications across every PAN in your family.</p>
          </div>
        </div>
      </div>
    </div>
  `,
})
export class AuthShell {
  readonly heading = input.required<string>();
  readonly altText = input.required<string>();
  readonly altLink = input.required<string>();
}

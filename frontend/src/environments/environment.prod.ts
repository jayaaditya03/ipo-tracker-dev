import packageInfo from '../../package.json';

export const environment = {
  appVersion: packageInfo.version,
  production: true,
  // Point this at the deployed Django API before a production build.
  apiUrl: 'http://localhost:8000/api'
};

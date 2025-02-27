#! /bin/python3
import numpy as np
from lenstronomy.Util import param_util
from lenstronomy.LensModel.Solver.lens_equation_solver import LensEquationSolver
from lenstronomy.LightModel.light_model import LightModel
from astropy.cosmology import FlatLambdaCDM
import scipy.stats as stats
import sncosmo
from math import ceil
import traceback
import time


class Supernova:

    def __init__(self, theta_E, z_lens, z_source, cosmo, source_x, source_y, num_images, differential_dust=False):
        """
        This class defines the supernova whose light is gravitationally lensed by the lens galaxy.

        :param theta_E: einstein radius of the lens galaxy (float)
        :param z_lens: redshift of the lens galaxy (float)
        :param z_source: redshift of the supernova (float)
        :param cosmo: instance of astropy containing the background cosmology
        :param source_x: x-position of the supernova relative to the lens galaxy in arcsec (float)
        :param source_y: y-position of the supernova relative to the lens galaxy in arcsec (float)
        """

        self.theta_E = theta_E
        self.z_lens = z_lens
        self.z_source = z_source
        self.cosmo = cosmo
        self.source_x = source_x
        self.source_y = source_y
        self.num_images = num_images
        self.differential_dust = differential_dust

    def get_image_pos_magnification(self, lens_model_class, kwargs_lens):
        """
        Calculates the image positions and magnifications using Lenstronomy functions.

        :param lens_model_class: Lenstronomy object returned from LensModel
        :param kwargs_lens: list of keyword arguments for the PEMD and external shear lens model
        :param min_distance: smallest distance ... equal to pixel size of telescope
        :param search_window: area in array to search for SN images
        :return: two numpy arrays of length [num_images] containing the image positions in arcsec,
                 one numpy array of length [num_images] with the macro magnification for each image
        """
        lensEquationSolver = LensEquationSolver(lens_model_class)
        x_image, y_image = lensEquationSolver.findBrightImage(self.source_x, self.source_y, kwargs_lens)

        macro_mag = lens_model_class.magnification(x_image, y_image, kwargs=kwargs_lens)
        macro_mag = np.abs(macro_mag)
        return x_image, y_image, macro_mag

    def host_light_model(self):
        """
        Uses lenstronomy to calculate the light model of the supernova host galaxy.
        Note: in our current set-up (using difference imageging), there is no light contribution from the host galaxy.

        :return: source_model_class: Lenstronomy object returned from LightModel corresponding to the host galaxy
                 kwargs_source: list of keywords arguments for the host light model
        """
        # No host light model in difference images
        source_model_list = ['SERSIC_ELLIPSE']
        phi_source, q_source = np.random.uniform(-np.pi / 2, np.pi / 2), np.random.uniform(0.2, 0.9)
        # if q_source not in [0,1]: continue
        e1, e2 = param_util.phi_q2_ellipticity(phi_source, q_source)
        kwargs_sersic_source = {'amp': 0, 'R_sersic': 0.1, 'n_sersic': 2, 'e1': e1, 'e2': e2,
                                'center_x': self.source_x, 'center_y': self.source_y}
        kwargs_source = [kwargs_sersic_source]
        source_model_class = LightModel(light_model_list=source_model_list)
        return source_model_class, kwargs_source

    def separation(self, x_image, y_image):
        """
        Calculates the maximum image separation.

        :param x_image: array of length [num_images] containing the x coordinates of the supernova images in arcsec
        :param y_image: array of length [num_images] containing the y coordinates of the supernova images in arcsec
        :return: maximum separation between images in arcsec (float)
        """
        if len(x_image) == 2:
            sep = ((x_image[0] - x_image[1])**2 + (y_image[0] - y_image[1])**2)**0.5
            return sep
        elif len(x_image) == 4:
            sep1 = ((x_image[0] - x_image[1]) ** 2 + (y_image[0] - y_image[1]) ** 2) ** 0.5
            sep2 = ((x_image[0] - x_image[2]) ** 2 + (y_image[0] - y_image[2]) ** 2) ** 0.5
            sep3 = ((x_image[0] - x_image[3]) ** 2 + (y_image[0] - y_image[3]) ** 2) ** 0.5
            sep4 = ((x_image[1] - x_image[2]) ** 2 + (y_image[1] - y_image[2]) ** 2) ** 0.5
            sep5 = ((x_image[1] - x_image[3]) ** 2 + (y_image[1] - y_image[3]) ** 2) ** 0.5
            sep6 = ((x_image[2] - x_image[3]) ** 2 + (y_image[2] - y_image[3]) ** 2) ** 0.5
            separations = np.array([sep1, sep2, sep3, sep4, sep5, sep6])
            max_sep = max(separations)
            return max_sep

    def get_sncosmo_filter(self, telescope, band):
        """
        Determines the name of the SNcosmo filter corresponding to a specific telescope and bandpass.

        :param telescope: Choose 'LSST' or 'ZTF'
        :param band: bandpass, choose between 'g', 'r', 'i', 'z', 'y' for LSST and 'g', 'r', 'i' for ZTF.
        :return: string containing SNcosmo name for the desired filter/bandpass.
        """

        if telescope == 'LSST':
            sncosmo_filter = 'lsst'+band

        elif telescope == 'JWST':
            sncosmo_filter = band

        elif telescope == 'HST':
            sncosmo_filter = band

        elif telescope == 'DECam':
            sncosmo_filter = 'des'+band

        # Create elif telescope == 'ZTF'

        return sncosmo_filter

    def peakphase(self, model, telescope, band, sampling=1.):
        """Determine phase of maximum flux for the given band/wavelength.
        This method generates the light curve in the given band/wavelength and
        finds the highest-flux point. It then finds the parabola that
        passes through this point and the two neighboring points, and
        returns the position of the peak of the parabola.
        Adapted from SNcosmo's source.peakphase

        :param model: SNcosmo model for the supernova light curve
        :param telescope: choose 'LSST' or 'ZTF'
        :param band: bandpass, choose between 'g', 'r', 'i', 'z', 'y' for LSST and 'g', 'r', 'i' for ZTF.
        :param sampling: sampling frequency (in days) to find the peak
        :returns The epoch (in days) where the light curve peaks in the specific band
        """

        # Array of phases to sample at.
        nsamples = int(ceil((model.maxtime() - model.mintime()) / sampling)) + 1
        phases = np.linspace(model.mintime(), model.maxtime(), nsamples)

        if band == 'r' and self.z_source > 1.6:
            return np.nan
        elif band == 'g' and self.z_source > 0.8:
            return np.nan

        sncosmo_filter = self.get_sncosmo_filter(telescope.telescope, band)

        fluxes = model.bandflux(sncosmo_filter, phases)

        i = np.argmax(fluxes)
        if (i == 0) or (i == len(phases) - 1):
            return phases[i]

        x = phases[i - 1: i + 2]
        y = fluxes[i - 1: i + 2]
        A = np.hstack([x.reshape(3, 1) ** 2, x.reshape(3, 1), np.ones((3, 1))])
        a, b, c = np.linalg.solve(A, y)

        return -b / (2 * a)

    def flux_ratio(self, model, macro_mag, micro_peak, telescope, band, add_microlensing):
        """
        Calculate the flux ratio between the brightest and faintest image.

        :param model: SNcosmo model for the supernova light curve
        :param macro_mag: array of length [num_images] containing the macro magnification of each image
        :param micro_peak: array of length [num_images] containing the microlensing contributions at peak
        :param telescope: choose 'LSST' or 'ZTF'
        :param band: bandpass, choose between 'g', 'r', 'i', 'z', 'y' for LSST and 'g', 'r', 'i' for ZTF.
        :param add_microlensing: bool. if False: only compute macro magnification. if True: also add microlensing
                contributions to the light curves
        :return: flux ratio between the brightest and faintest image (float)
        """

        sncosmo_filter = self.get_sncosmo_filter(telescope.telescope, band)

        if add_microlensing:
            zeropoint = sncosmo.ABMagSystem(name='ab').zpbandflux(sncosmo_filter)
            magnitude_macro = model.bandmag(sncosmo_filter, time=0, magsys='ab')
            magnitude_macro -= 2.5 * np.log10(macro_mag)
            magnitude_micro = magnitude_macro + micro_peak
            flux = 10**(magnitude_micro / -2.5) * zeropoint

        else:
            flux = model.bandflux(sncosmo_filter, time=0)
            flux *= macro_mag

        flux_ratio = flux[1] / flux[0]
        return flux_ratio

    def check_detectability_peak(self, telescope, model, macro_mag, td_images, add_microlensing, microlensing, micro_contributions,
                                 detection_threshold=0.2, lower_lim_mag=False):

        """
        Check whether the lensed SN peak brightness can be detected by the telescope at peak brightness.
        If it is detectable in any filter, return True.

        :param telescope: choose between 'LSST' and 'ZTF'
        :param model: SNcosmo model for the supernova light curve
        :param macro_mag: array of length [num_images] containing the macro magnification of each image
        :param micro_peak: array of length [num_images] containing the microlensing contributions at peak
        :param add_microlensing: bool. if False: no microlensing. if True: also add microlensing to the peak
        :param detection_threshold: magnitude difference from limiting magnitude required for a detection
                (Following the definition from Wojtak et al. 2019, detection_threshold = 0.2 mag)
        :param lower_lim_mag: if True: scan 2 magnitudes fainter than the limiting magnitude
        :return: bool. True: detectable in at least 1 filter. False: not detectable in any filter.
        """

        for band in telescope.bandpasses:

            if band == 'r' and self.z_source > 1.6:
                continue
            elif band == 'g' and self.z_source > 0.8:
                continue

            if add_microlensing:
                micro_day = np.array(microlensing.micro_snapshot(micro_contributions, td_images, 0, band, peak=True))
            else:
                micro_day = np.nan

            num_images = len(macro_mag)

            if num_images == 2:
                # Check if the flux ratio is between 0.1 and 10
                flux_ratio = self.flux_ratio(model, macro_mag, micro_day, telescope, band, add_microlensing)
                if flux_ratio < 0.1 or flux_ratio > 10:
                    continue

            sncosmo_filter = self.get_sncosmo_filter(telescope.telescope, band)

            peak_phase = self.peakphase(model, telescope, band)
            peak_brightness = model.bandmag(sncosmo_filter, time=peak_phase, magsys='ab')
            peak_brightness -= 2.5 * np.log10(macro_mag)

            if add_microlensing:
                peak_brightness += micro_day

            limiting_magnitude = telescope.single_band_properties(band)[4]

            if lower_lim_mag:
                limiting_magnitude += 2

            if num_images == 2:
                if len(peak_brightness[peak_brightness < (limiting_magnitude - detection_threshold)]) == 2:
                    return True

            elif num_images == 4:
                if len(peak_brightness[peak_brightness < (limiting_magnitude - detection_threshold)]) >= 3:
                    return True
        return False

    def check_detectability(self, telescope, model, macro_mag, brightness_obs, obs_snr, limiting_mags, obs_filters, micro_peak, add_microlensing):
        """
        Check whether the lensed SN peak brightness and flux ratio can be detected by the telescope.
        If it is detectable in any filter, return True.

        :param telescope: choose between 'LSST' and 'ZTF'
        :param model: SNcosmo model for the supernova light curve
        :param macro_mag: array of length [num_images] containing the macro magnification of each image
        :param brightness_obs: array of length [num_observations, num_images] containing the brightness of each observation
        :param obs_snr: array of shape [N_observations, N_images] containing the S/N ratio for each image
        :param limiting_mags: array of length [num_observations] containing the limiting magnitudes (5 sigma depths)
        :param obs_filters: array of length [num_observations] containing the filter used for each observation
        :param micro_peak: array of length [num_images] containing the microlensing contributions at peak
        :param add_microlensing: bool. if False: no microlensing. if True: also add microlensing to the peak
        :return: bool. True: detectable in at least 1 filter. False: not detectable in any filter.
        """

        for band in telescope.bandpasses:

            if band == 'r' and self.z_source > 1.6:
                continue
            elif band == 'g' and self.z_source > 0.8:
                continue

            num_images = len(macro_mag)

            if num_images == 2:
                # Check if the flux ratio is between 0.1 and 10
                # Note: this only checks the flux ratio at peak, not for every observation!
                flux_ratio = self.flux_ratio(model, macro_mag, micro_peak, telescope, band, add_microlensing)
                if flux_ratio < 0.1 or flux_ratio > 10:
                    continue

            # Check if S/N ratio > 5

            mask = np.where(obs_filters == band)[0]
            if len(obs_snr[mask]) == 0:
                continue

            try:
                detections = np.nanmax(obs_snr[mask], axis=0)
                detections_index = np.nanargmax(obs_snr[mask], axis=0)
            except:
                return False

            if num_images == 2:
                if (detections > 5).sum() == 2:
                        return True

            elif num_images == 4:
                if (detections > 5).sum() > 2:
                        return True

        return False

    def brightest_obs_bands(self, telescope, macro_mag, brightness_obs, obs_filters):
        """
        Compute for each band the magnitudes of the brightest observation.

        :param telescope: choose between 'LSST' and 'ZTF'
        :param macro_mag: array of length [num_images] containing the macro magnification of each image
        :param brightness_obs: array of length [num_observations, num_images] containing the brightness of each observation
        :param obs_filters: array of length [num_observations] containing the filter used for each observation
        :return: array of [num_filters, num_images] containing the peak brightness for each filter/bandpass.
                 if no observations are made in a filter, the array contains np.nans
        """

        num_images = len(macro_mag)
        obs_peak = np.zeros((len(telescope.bandpasses), num_images))

        for b in range(len(telescope.bandpasses)):

            band = telescope.bandpasses[b]

            indices = np.where(np.array(obs_filters) == band)[0]

            # If no observations in this band
            if len(indices) == 0:
                obs_peak[b] = np.nan * np.ones(num_images)
                continue

            # Save the brightest observations in the band
            obs_peak[b] = np.min(brightness_obs[indices], axis=0)

        return obs_peak

    def M_obs(self, x1, c, M_corrected):
        """
        Applies the Tripp Formula to correlate absolute magnitude with colour and stretch.
        Values for Alpha and Beta are taken from Scolnic & Kessler (2016).

        :param x1: stretch parameter for the SALT3 model
        :param c: colour parameter for the SALT3 model
        :param M_corrected: The absolute magnitude of the supernova without stretch and colour correlations
        :return: M_observed: The absolute magnitude of the supernova correlated with its stretch and colour
        """
        Alpha = 0.14
        Beta = 3.1
        M_observed = - Alpha * x1 + Beta * c + M_corrected
        return M_observed

    def light_curve(self, t0=None, x1=None, c=None, mw_ebv=None, host_rv=None, host_ebv=None, lens_rv=None, lens_ebv=None, int_scatter=True):
        """
        Samples light curve parameters from stretch and colour distributions based on Scolnic & Kessler (2016)
        and returns a type Ia SN light curve model from SNcosmo using the SALT3 model.

        :param z_source: redshift of the supernova
        :return: SNcosmo model of the supernova light curve, stretch parameter, colour parameter, MW dust contribution,
                 observed absolute magnitude
        """
        H_0 = self.cosmo.H(0).value
        H_0_fid = 74.03                                      # SH0ES 2019 value
        M_fid = -19.24                                       # Absolute magnitude corresponding to SH0ES 2019 H0 value

        # Create MW dust object
        mw_dustmodel = sncosmo.F99Dust(r_v=3.1)

        # Sample E(B-V)_MW
        if mw_ebv is None:
            mw_ebv = np.random.uniform(0, 0.2)
        
        # Create lens dust object
        if lens_rv is None:
            lens_rv = 2.0
        lens_dustmodel = sncosmo.F99Dust(r_v=lens_rv)

        # Sample E(B-V)_lens
        if self.differential_dust:
            if lens_ebv is None:
                lens_ebv = np.random.uniform(0, 0.2, self.num_images)
        else:
            if lens_ebv is None:
                lens_ebv = np.random.uniform(0, 0.2)

        # Create host dust object
        if host_rv is None:
            host_rv = 2.0
        host_dustmodel = sncosmo.F99Dust(r_v=host_rv)

        # Sample E(B-V)_host
        if host_ebv is None:
            host_ebv = np.random.uniform(0, 0.2)

        if t0 is None:
            t0 = 0.

        # Sample stretch parameter
        if x1 is None:
            x1 = stats.skewnorm.rvs(-8.241, 1.2311, 1.6712)

        # Sample colour parameter
        if c is None:
            c = stats.skewnorm.rvs(2.483, -0.08938, 0.1215)

        M_cosmo = 5 * np.log10(H_0 / H_0_fid) + M_fid        # Cosmology correction to absolute magnitude
        if int_scatter:
            M_corrected = np.random.normal(M_cosmo, 0.12)    # Absolute magnitude without colour/stretch correlation
        else:
            M_corrected = M_cosmo                            # (optionally without intrinsic scatter)
        M_observed = self.M_obs(x1, c, M_corrected)          # Absolute magnitude with colour/stretch correlation

        # Create sncosmo model
        model = sncosmo.Model(source='salt3', effects=[mw_dustmodel, lens_dustmodel, host_dustmodel], effect_names=['mw', 'lens', 'host'],
                              effect_frames=['obs', 'free', 'rest'])
        
        # Set model parameters
        model.set(z=self.z_source, t0=t0, x1=x1, c=c, mwebv=mw_ebv, lensz=self.z_lens, lensebv=lens_ebv, hostebv=host_ebv)
        model.set_source_peakabsmag(M_observed, 'bessellb', 'ab', cosmo=self.cosmo)
        x0 = model.get('x0')
        model.set(x0=x0)
        return model, x1, c, mw_ebv, lens_ebv, host_ebv, M_observed

    def get_m_lens(self, telescope):
        """
        Calculates the apparent magnitude of a vanilla type Ia SN at the lens redshift (in order to check mag method).
        :param telescope: class of telescope ('LSST' or 'ZTF')
        :return: array of len N_bands containing the apparent magnitude of a type Ia at the lens redshift for each band
        """

        model_vanilla = sncosmo.Model(source='salt3')
        model_vanilla.set(z=self.z_lens, t0=0, x1=0, c=0)
        model_vanilla.set_source_peakabsmag(-19.4, 'bessellb', 'ab', cosmo=self.cosmo)

        m_lens = {}

        for band in telescope.bandpasses:

            if band == 'r' and self.z_source > 1.6:
                m_lens[band] = np.nan
                continue
            elif band == 'g' and self.z_source > 0.8:
                m_lens[band] = np.nan
                continue

            sncosmo_filter = self.get_sncosmo_filter(telescope.telescope, band)
            peak_phase = self.peakphase(model_vanilla, telescope, band)

            m_lens_band = model_vanilla.bandmag(sncosmo_filter, time=peak_phase, magsys='ab')
            m_lens[band] = m_lens_band

        return m_lens

    def get_app_magnitude(self, model, day, macro_mag, td_images, micro_day, telescope_class, band, lim_mag, target_snr, add_microlensing):
        """
        Calculate the apparent magnitude + error for each supernova image at a certain time stamp.

        :param model: SNcosmo model for the supernova light curve
        :param day: time stamp of observation
        :param macro_mag: array of length [num_images] containing the macro magnification of each image
        :param td_images: array of length [num_images] containing the time delays between the supernova images
        :param micro_day: array of length [num_images] containing the microlensing contribution corresponding to the
        :param telescope_class: class of telescope ('LSST' or 'ZTF')
        :param band: bandpass, choose between 'g', 'r', 'i', 'z', 'y' for LSST and 'g', 'r', 'i' for ZTF.
        :param lim_mag: limiting magnitude of the specific observation in the specific band (takes into account weather)
        :param add_microlensing: bool. if False: only compute macro magnification. if True: also add microlensing
                contributions to the light curves
        :return: app_mag_model: array of length [num_images] containing the apparent magnitude from the model
                 app_mag_obs: array of length [num_images] containing the observed (perturbed) apparent magnitude
                 app_mag_error: array of length [num_images] containing the apparent magnitude error
        """

        sncosmo_filter = self.get_sncosmo_filter(telescope_class.telescope, band)
        zeropoint = telescope_class.single_band_properties(band)[3]

        # Calculate magnitude, add microlensing, convert back to flux
        app_mag_ps = model.bandmag(sncosmo_filter, time=day - td_images, magsys='ab')
        app_mag_ps -= 2.5 * np.log10(macro_mag)

        if add_microlensing:
            app_mag_ps += micro_day

        flux_micro = 10**((zeropoint - app_mag_ps)/2.5)
        flux_ps = model.bandflux(sncosmo_filter, time=day - td_images, zp=zeropoint, zpsys='ab')

        # Apply macro magnification to image fluxes
        flux_ps *= macro_mag
        flux_ps[flux_ps < 0.0] = 0.0

        if np.isin(telescope_class.telescope, ['JWST', 'HST']):
            # Calculate flux error from target SNR
            flux_error = flux_ps / target_snr
        else:
            # Calculate limiting flux from zero point and limiting magnitude
            lim_flux = 10**((zeropoint - lim_mag)/2.5)
            flux_error = lim_flux / 5

        # Perturb the flux according to the flux error (from the sky signal)
        flux_perturbation = np.random.normal(loc=0, scale=abs(flux_error))
        new_flux_ps = flux_ps + flux_perturbation  # Remove!!!
        new_flux_ps[new_flux_ps < 0.0] = 0.0
        new_flux_ps[flux_ps <= flux_error] = 0.0

        new_flux_micro = flux_micro + flux_perturbation  # Remove!!
        new_flux_micro[new_flux_micro < 0.0] = 0.0
        new_flux_micro[flux_micro <= flux_error] = 0.0

        # Calculate S/N
        snr = new_flux_ps / flux_error
        snr_micro = new_flux_micro / flux_error

        # Convert to magnitudes
        app_mag_model = zeropoint - 2.5 * np.log10(flux_ps)

        app_mag_obs = zeropoint - 2.5*np.log10(new_flux_ps)
        app_mag_obs = np.nan_to_num(app_mag_obs, nan=np.inf)
        app_mag_error = abs(-2.5 * flux_error / (new_flux_ps * np.log(10)))
        app_mag_obs[app_mag_obs > 30] = np.inf
        app_mag_error[app_mag_obs > 30] = np.nan

        app_mag_micro = zeropoint - 2.5 * np.log10(new_flux_micro)
        app_mag_micro = np.nan_to_num(app_mag_micro, nan=np.inf)
        app_mag_micro_error = abs(-2.5 * flux_error / (new_flux_micro * np.log(10)))
        app_mag_micro[app_mag_micro > 30] = np.inf
        app_mag_micro_error[app_mag_micro > 30] = np.nan

        return app_mag_model, app_mag_obs, app_mag_error, snr, app_mag_micro, app_mag_micro_error, snr_micro, app_mag_ps

    def get_mags_unresolved(self, obs_mag, telescope_class, obs_filters, obs_lim_mag, filler=np.nan):
        """
        Calculate the apparent magnitude for all images together (unresolved)

        :param obs_mag: array of shape [N_observations, N_images] that contains the apparent magnitudes for each
            observation and each image.
        :param telescope_class: class of telescope ('LSST' or 'ZTF')
        :param obs_filters: array of length [num_observations] containing the filter used for each observation
        :param obs_lim_mag: array of length [num_observations] containing the limiting magnitudes per observation
        :param filler: choice of filler for observations dimmer than 50 magnitudes
        :return: array of len N_observations containing the unresolved apparent magnitude for all images together
        """

        if len(obs_mag) == 0:
            return np.nan, np.nan, np.nan

        # Get zero points
        zeropoints = np.ones_like(obs_mag)

        if obs_mag.ndim == 2:
            for f in range(len(zeropoints)):
                zeropoints[f] *= telescope_class.single_band_properties(obs_filters[f])[3]
        else:
            zeropoints *= telescope_class.single_band_properties(obs_filters[0])[3]

        # Get unresolved fluxes

        fluxes = 10 ** ((zeropoints - obs_mag) / 2.5)
        fluxes[obs_mag == np.inf] = 0.0

        if obs_mag.ndim == 2:
            fluxes_unresolved = np.sum(fluxes, axis=1)
            zeropoints = zeropoints[:, 0]
        else:
            fluxes_unresolved = np.sum(fluxes)
            zeropoints = zeropoints[0]

        # Get unresolved magnitudes

        mags_unresolved = zeropoints - 2.5 * np.log10(fluxes_unresolved)

        if not filler == None:
            mags_unresolved[mags_unresolved >= 50] = filler

        # Get magnitude error

        lim_flux = 10 ** ((zeropoints - obs_lim_mag) / 2.5)
        flux_errors = lim_flux / 5

        snr_unresolved = fluxes_unresolved / flux_errors

        unresolved_mag_error = abs(-2.5 * flux_errors / (fluxes_unresolved * np.log(10)))

        if obs_mag.ndim == 2:
            unresolved_mag_error[unresolved_mag_error > 50] = 50
        else:
            if unresolved_mag_error > 50:
                unresolved_mag_error = 50

        return mags_unresolved, unresolved_mag_error, snr_unresolved



def main():

    cosmo = FlatLambdaCDM(H0=70, Om0=0.3, Ob0=0.05)
    sn = Supernova(1.0, 0.3, 0.8, cosmo, 0.1, 0.2)
    print("SN redshift: ", sn.z_source)
    print(sn.light_curve(1))


if __name__ == '__main__':
    main()

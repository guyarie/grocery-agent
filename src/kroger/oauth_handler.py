"""
OAuth Handler for Kroger OAuth2 authentication flow.

This module manages the OAuth2 authorization flow for Kroger API access,
including token exchange, refresh, and storage.
"""

import logging
import requests
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from urllib.parse import urlencode
from sqlalchemy.orm import Session

from ..models import KrogerOAuthToken, User
from ..config import get_app_config, get_kroger_config
from ..exceptions import KrogerAPIError
from ..utils.api_logging import log_api_request, log_api_response, log_api_error

logger = logging.getLogger(__name__)


class OAuthHandler:
    """
    Handles Kroger OAuth2 authorization flow.
    
    Responsibilities:
    - Generate authorization URLs
    - Exchange authorization codes for access tokens
    - Refresh expired access tokens
    - Store and retrieve tokens from database
    - Load test user credentials from configuration
    """
    
    def __init__(self, db: Session):
        """
        Initialize OAuth handler with database session.
        
        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.kroger_config = get_kroger_config()
        
        # Load OAuth configuration
        self.client_id = self.kroger_config.get('client_id', '')
        self.client_secret = self.kroger_config.get('client_secret', '')
        self.authorization_url = self.kroger_config.get('authorization_url', '')
        self.token_url = self.kroger_config.get('token_url', '')
        self.redirect_uri = self.kroger_config.get('redirect_uri', '')
        self.scope = self.kroger_config.get('scope', 'cart.basic:write')
        
        # Validate required configuration
        if not self.client_id or not self.client_secret:
            raise KrogerAPIError("Kroger OAuth credentials not configured")
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """
        Generate Kroger OAuth2 authorization URL.
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Authorization URL with required parameters
            
        Example:
            https://api.kroger.com/v1/connect/oauth2/authorize?
            scope=cart.basic:write&response_type=code&client_id=...&redirect_uri=...
        """
        params = {
            'scope': self.scope,
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri
        }
        
        if state:
            params['state'] = state
        
        auth_url = f"{self.authorization_url}?{urlencode(params)}"
        logger.info(f"Generated authorization URL with scope: {self.scope}")
        
        return auth_url
    
    def exchange_code_for_token(self, code: str, user_id: str) -> KrogerOAuthToken:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from Kroger OAuth callback
            user_id: User ID to associate token with
            
        Returns:
            KrogerOAuthToken object with access and refresh tokens
            
        Raises:
            KrogerAPIError: If token exchange fails
        """
        try:
            # Prepare token request
            auth_string = f"{self.client_id}:{self.client_secret}"
            auth_bytes = auth_string.encode('utf-8')
            auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': f'Basic {auth_b64}'
            }
            
            data = {
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': self.redirect_uri
            }
            
            logger.info(f"Exchanging authorization code for token (user_id: {user_id})")
            
            # Log API request
            start_time = log_api_request(
                api_name='Kroger OAuth',
                method='POST',
                url=self.token_url,
                headers=headers,
                body=data
            )
            
            # Make token request
            response = requests.post(
                self.token_url,
                headers=headers,
                data=data,
                timeout=30
            )
            
            # Log API response
            log_api_response(
                api_name='Kroger OAuth',
                status_code=response.status_code,
                response_body=response.json() if response.text else None,
                start_time=start_time
            )
            
            if response.status_code != 200:
                error_msg = f"Token exchange failed: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise KrogerAPIError(error_msg)
            
            token_data = response.json()
            
            # Calculate token expiration
            expires_in = token_data.get('expires_in', 3600)
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            # Create or update token record
            token = self._store_token(
                user_id=user_id,
                access_token=token_data['access_token'],
                refresh_token=token_data['refresh_token'],
                token_type=token_data.get('token_type', 'Bearer'),
                expires_at=expires_at,
                scope=token_data.get('scope', self.scope)
            )
            
            logger.info(f"Successfully exchanged code for token (user_id: {user_id})")
            return token
            
        except requests.RequestException as e:
            error_msg = f"Network error during token exchange: {str(e)}"
            log_api_error('Kroger OAuth', e, 'POST', self.token_url)
            raise KrogerAPIError(error_msg)
        except KeyError as e:
            error_msg = f"Invalid token response format: missing {str(e)}"
            logger.error(error_msg)
            raise KrogerAPIError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during token exchange: {str(e)}"
            logger.error(error_msg)
            raise KrogerAPIError(error_msg)
    
    def refresh_access_token(self, refresh_token: str, user_id: str) -> KrogerOAuthToken:
        """
        Refresh expired access token using refresh token.
        
        Args:
            refresh_token: Refresh token from previous authorization
            user_id: User ID to associate refreshed token with
            
        Returns:
            KrogerOAuthToken object with new access token
            
        Raises:
            KrogerAPIError: If token refresh fails
        """
        try:
            # Prepare refresh request
            auth_string = f"{self.client_id}:{self.client_secret}"
            auth_bytes = auth_string.encode('utf-8')
            auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': f'Basic {auth_b64}'
            }
            
            data = {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token
            }
            
            logger.info(f"Refreshing access token (user_id: {user_id})")
            
            # Log API request
            start_time = log_api_request(
                api_name='Kroger OAuth',
                method='POST',
                url=self.token_url,
                headers=headers,
                body=data
            )
            
            # Make refresh request
            response = requests.post(
                self.token_url,
                headers=headers,
                data=data,
                timeout=30
            )
            
            # Log API response
            log_api_response(
                api_name='Kroger OAuth',
                status_code=response.status_code,
                response_body=response.json() if response.text else None,
                start_time=start_time
            )
            
            if response.status_code != 200:
                error_msg = f"Token refresh failed: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise KrogerAPIError(error_msg)
            
            token_data = response.json()
            
            # Calculate token expiration
            expires_in = token_data.get('expires_in', 3600)
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            # Update token record
            token = self._store_token(
                user_id=user_id,
                access_token=token_data['access_token'],
                refresh_token=token_data['refresh_token'],
                token_type=token_data.get('token_type', 'Bearer'),
                expires_at=expires_at,
                scope=token_data.get('scope', self.scope)
            )
            
            logger.info(f"Successfully refreshed access token (user_id: {user_id})")
            return token
            
        except requests.RequestException as e:
            error_msg = f"Network error during token refresh: {str(e)}"
            log_api_error('Kroger OAuth', e, 'POST', self.token_url)
            raise KrogerAPIError(error_msg)
        except KeyError as e:
            error_msg = f"Invalid refresh response format: missing {str(e)}"
            logger.error(error_msg)
            raise KrogerAPIError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during token refresh: {str(e)}"
            logger.error(error_msg)
            raise KrogerAPIError(error_msg)
    
    def get_valid_token(self, user_id: str) -> str:
        """
        Get valid access token for user, refreshing if needed.
        
        Args:
            user_id: User ID to get token for
            
        Returns:
            Valid access token string
            
        Raises:
            KrogerAPIError: If no token exists or refresh fails
        """
        # Get most recent token for user
        token = self.db.query(KrogerOAuthToken).filter(
            KrogerOAuthToken.user_id == user_id
        ).order_by(KrogerOAuthToken.updated_at.desc()).first()
        
        if not token:
            error_msg = f"No OAuth token found for user {user_id}"
            logger.error(error_msg)
            raise KrogerAPIError(error_msg)
        
        # Check if token is expired (with 5 minute buffer)
        now = datetime.utcnow()
        buffer = timedelta(minutes=5)
        
        if now + buffer >= token.expires_at:
            logger.info(f"Token expired or expiring soon, refreshing (user_id: {user_id})")
            token = self.refresh_access_token(token.refresh_token, user_id)
        
        return token.access_token
    
    def _store_token(
        self,
        user_id: str,
        access_token: str,
        refresh_token: str,
        token_type: str,
        expires_at: datetime,
        scope: str
    ) -> KrogerOAuthToken:
        """
        Store or update OAuth token in database.
        
        Args:
            user_id: User ID to associate token with
            access_token: OAuth access token
            refresh_token: OAuth refresh token
            token_type: Token type (usually "Bearer")
            expires_at: Token expiration datetime
            scope: OAuth scope
            
        Returns:
            KrogerOAuthToken object
        """
        # Check if token already exists for user
        existing_token = self.db.query(KrogerOAuthToken).filter(
            KrogerOAuthToken.user_id == user_id
        ).order_by(KrogerOAuthToken.updated_at.desc()).first()
        
        if existing_token:
            # Update existing token
            existing_token.access_token = access_token
            existing_token.refresh_token = refresh_token
            existing_token.token_type = token_type
            existing_token.expires_at = expires_at
            existing_token.scope = scope
            existing_token.updated_at = datetime.utcnow()
            
            self.db.commit()
            self.db.refresh(existing_token)
            
            logger.info(f"Updated OAuth token for user {user_id}")
            return existing_token
        else:
            # Create new token
            new_token = KrogerOAuthToken(
                user_id=user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                token_type=token_type,
                expires_at=expires_at,
                scope=scope
            )
            
            self.db.add(new_token)
            self.db.commit()
            self.db.refresh(new_token)
            
            logger.info(f"Created new OAuth token for user {user_id}")
            return new_token
    
    def get_test_user_config(self) -> Dict[str, Any]:
        """
        Get test user configuration from config file.
        
        Returns:
            Dictionary with test user configuration (location_id, modality)
        """
        test_user_config = self.kroger_config.get('test_user', {})
        
        return {
            'location_id': test_user_config.get('location_id', ''),
            'modality': test_user_config.get('modality', 'PICKUP')
        }
